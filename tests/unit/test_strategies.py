"""Unit tests for hft_backtest.engine.context, hft_backtest.strategies."""

from __future__ import annotations

from pathlib import Path

import pytest

from hft_backtest.data.event_stream import EventStream
from hft_backtest.data.events import Level, LobSnapshot, MarketEvent, Side, Trade
from hft_backtest.data.loaders import LobLoader, TradesLoader
from hft_backtest.engine import Backtest, EngineContext
from hft_backtest.execution.matcher import MatchingEngine
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders import (
    OrderAlreadyDoneError,
    OrderManager,
    OrderStatus,
    UnknownOrderError,
)
from hft_backtest.strategies import NaiveMarketMaker, Strategy

SAMPLE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "data" / "samples"
)
SAMPLE_LOB = SAMPLE_DIR / "lob_sample.csv"
SAMPLE_TRADES = SAMPLE_DIR / "trades_sample.csv"


# =========================================================================
# EngineContext
# =========================================================================


def _ctx(now: int = 1000, book: OrderBook | None = None) -> tuple[EngineContext, OrderManager]:
    om = OrderManager()
    return EngineContext(book or OrderBook(), om, now), om


def test_context_now_is_event_timestamp() -> None:
    ctx, _ = _ctx(now=42)
    assert ctx.now == 42


def test_context_book_is_engine_book() -> None:
    book = OrderBook()
    ctx, _ = _ctx(book=book)
    assert ctx.book is book


def test_context_place_creates_order_and_uses_now_as_ts() -> None:
    ctx, om = _ctx(now=500)
    o = ctx.place(Side.BUY, 100.0, 2.0)
    assert o.ts == 500
    assert o.side is Side.BUY
    assert o.price == 100.0
    assert o.size == 2.0
    assert o.status is OrderStatus.NEW
    assert list(om.active()) == [o]


def test_context_cancel_marks_cancelled() -> None:
    ctx, _ = _ctx()
    o = ctx.place(Side.BUY, 100.0, 1.0)
    cancelled = ctx.cancel(o.id)
    assert cancelled is o
    assert o.status is OrderStatus.CANCELLED


def test_context_cancel_unknown_raises() -> None:
    ctx, _ = _ctx()
    with pytest.raises(UnknownOrderError):
        ctx.cancel(99)


def test_context_cancel_already_done_raises() -> None:
    ctx, _ = _ctx()
    o = ctx.place(Side.BUY, 100.0, 1.0)
    ctx.cancel(o.id)
    with pytest.raises(OrderAlreadyDoneError):
        ctx.cancel(o.id)


# =========================================================================
# Strategy base + engine integration
# =========================================================================


class _Recording(Strategy):
    """Records every (event_timestamp, ctx.now, type) it sees."""

    def __init__(self) -> None:
        self.seen: list[tuple[int, int, str]] = []

    def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:
        self.seen.append((event.timestamp, ctx.now, type(event).__name__))


def test_engine_calls_strategy_on_each_event_in_order() -> None:
    s = _Recording()
    events: list[MarketEvent] = [
        LobSnapshot(timestamp=100, bids=(), asks=()),
        Trade(timestamp=200, side=Side.BUY, price=1.0, amount=1.0),
        LobSnapshot(timestamp=300, bids=(), asks=()),
    ]
    Backtest(events, OrderBook(), OrderManager(), MatchingEngine(), strategy=s).run()
    assert s.seen == [
        (100, 100, "LobSnapshot"),
        (200, 200, "Trade"),
        (300, 300, "LobSnapshot"),
    ]


def test_engine_default_strategy_is_no_op() -> None:
    """Backtest without a strategy still runs cleanly (M5 contract)."""
    events: list[MarketEvent] = [Trade(timestamp=1, side=Side.BUY, price=1.0, amount=1.0)]
    fills = Backtest(events, OrderBook(), OrderManager(), MatchingEngine()).run()
    assert fills == []


def test_strategy_default_on_event_is_no_op() -> None:
    """Bare `Strategy()` is a usable plumbing placeholder."""
    s = Strategy()
    events: list[MarketEvent] = [Trade(timestamp=1, side=Side.BUY, price=1.0, amount=1.0)]
    om = OrderManager()
    Backtest(events, OrderBook(), om, MatchingEngine(), strategy=s).run()
    assert len(om) == 0  # no orders placed


def test_strategy_orders_dont_fill_against_current_event() -> None:
    """A buy placed in response to event E does not match against E.
    Strategy reacts after matching — that's correct latency semantics.
    """

    class JoinAtTradePrice(Strategy):
        def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:
            if isinstance(event, Trade):
                ctx.place(Side.BUY, event.price, 1.0)

    om = OrderManager()
    events: list[MarketEvent] = [
        Trade(timestamp=100, side=Side.SELL, price=99.0, amount=1.0),
        # strategy places buy @ 99 here, in response to ^^
        Trade(timestamp=200, side=Side.SELL, price=99.0, amount=1.0),
        # this one matches the resting buy
    ]
    fills = Backtest(
        events, OrderBook(), om, MatchingEngine(), strategy=JoinAtTradePrice()
    ).run()
    assert len(fills) == 1
    assert fills[0].timestamp == 200


def test_strategy_can_cancel_via_context() -> None:
    placed: list[int] = []
    cancelled: list[int] = []

    class P(Strategy):
        def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:
            if isinstance(event, LobSnapshot) and not placed:
                placed.append(ctx.place(Side.BUY, 1.0, 1.0).id)
            elif placed and not cancelled:
                cancelled.append(ctx.cancel(placed[0]).id)

    events: list[MarketEvent] = [
        LobSnapshot(timestamp=1, bids=(), asks=()),
        LobSnapshot(timestamp=2, bids=(), asks=()),
    ]
    om = OrderManager()
    Backtest(events, OrderBook(), om, MatchingEngine(), strategy=P()).run()
    assert placed == cancelled
    assert om.get(placed[0]).status is OrderStatus.CANCELLED


# =========================================================================
# NaiveMarketMaker
# =========================================================================


def _book_with_mid(bid: float, ask: float, ts: int = 1000) -> OrderBook:
    book = OrderBook()
    book.apply(LobSnapshot(timestamp=ts, bids=(Level(bid, 1.0),), asks=(Level(ask, 1.0),)))
    return book


def _trade(ts: int) -> Trade:
    return Trade(timestamp=ts, side=Side.BUY, price=1.0, amount=1.0)


def test_mm_rejects_invalid_params() -> None:
    with pytest.raises(ValueError, match="half_spread"):
        NaiveMarketMaker(half_spread=-1.0, size=1.0)
    with pytest.raises(ValueError, match="size"):
        NaiveMarketMaker(half_spread=0.5, size=0.0)
    with pytest.raises(ValueError, match="repost_threshold"):
        NaiveMarketMaker(half_spread=0.5, size=1.0, repost_threshold=-0.1)


def test_mm_does_nothing_when_book_has_no_mid() -> None:
    mm = NaiveMarketMaker(half_spread=0.5, size=1.0)
    om = OrderManager()
    ctx = EngineContext(OrderBook(), om, now=100)
    mm.on_event(_trade(100), ctx)
    assert len(om) == 0


def test_mm_posts_buy_and_sell_around_mid() -> None:
    mm = NaiveMarketMaker(half_spread=0.5, size=2.0)
    om = OrderManager()
    book = _book_with_mid(bid=99.0, ask=101.0, ts=100)
    ctx = EngineContext(book, om, now=100)
    mm.on_event(_trade(100), ctx)

    active = list(om.active())
    assert len(active) == 2
    buy = next(o for o in active if o.side is Side.BUY)
    sell = next(o for o in active if o.side is Side.SELL)
    assert buy.price == 99.5  # mid 100 - half 0.5
    assert sell.price == 100.5
    assert buy.size == 2.0
    assert sell.size == 2.0


def test_mm_does_not_repost_when_mid_unchanged() -> None:
    mm = NaiveMarketMaker(half_spread=0.5, size=1.0)
    om = OrderManager()
    book = _book_with_mid(bid=99.0, ask=101.0, ts=100)

    mm.on_event(_trade(100), EngineContext(book, om, now=100))
    first_ids = {o.id for o in om.active()}

    # Same mid on the next event — no repost.
    mm.on_event(_trade(200), EngineContext(book, om, now=200))
    second_ids = {o.id for o in om.active()}
    assert first_ids == second_ids
    assert len(om) == 2  # no extra orders created


def test_mm_cancels_and_reposts_when_mid_moves() -> None:
    mm = NaiveMarketMaker(half_spread=0.5, size=1.0)
    om = OrderManager()
    book1 = _book_with_mid(bid=99.0, ask=101.0)
    mm.on_event(_trade(100), EngineContext(book1, om, now=100))
    first_ids = {o.id for o in om.active()}

    book2 = _book_with_mid(bid=101.0, ask=103.0)  # mid 100 -> 102
    mm.on_event(_trade(200), EngineContext(book2, om, now=200))

    second_active = list(om.active())
    assert len(second_active) == 2
    assert {o.id for o in second_active}.isdisjoint(first_ids)
    new_buy = next(o for o in second_active if o.side is Side.BUY)
    new_sell = next(o for o in second_active if o.side is Side.SELL)
    assert new_buy.price == 101.5
    assert new_sell.price == 102.5


def test_mm_repost_threshold_suppresses_small_moves() -> None:
    mm = NaiveMarketMaker(half_spread=0.5, size=1.0, repost_threshold=0.5)
    om = OrderManager()
    book1 = _book_with_mid(bid=99.0, ask=101.0)
    mm.on_event(_trade(100), EngineContext(book1, om, now=100))
    first_ids = {o.id for o in om.active()}

    # Mid moves 100 -> 100.4: within threshold (0.5), no repost.
    book2 = _book_with_mid(bid=99.4, ask=101.4)
    mm.on_event(_trade(200), EngineContext(book2, om, now=200))
    assert {o.id for o in om.active()} == first_ids

    # Mid moves 100 -> 100.6: above threshold, repost.
    book3 = _book_with_mid(bid=99.6, ask=101.6)
    mm.on_event(_trade(300), EngineContext(book3, om, now=300))
    assert {o.id for o in om.active()}.isdisjoint(first_ids)


def test_mm_handles_filled_quote_without_raising() -> None:
    """When the matcher fills our buy, the next repost should swallow the
    OrderAlreadyDoneError on the now-FILLED order id."""
    mm = NaiveMarketMaker(half_spread=0.5, size=1.0)
    om = OrderManager()
    book = _book_with_mid(bid=99.0, ask=101.0)
    mm.on_event(_trade(100), EngineContext(book, om, now=100))

    buy = next(o for o in om.active() if o.side is Side.BUY)
    buy.status = OrderStatus.FILLED
    buy.filled_size = buy.size

    # Mid moves to trigger repost.
    book2 = _book_with_mid(bid=101.0, ask=103.0)
    mm.on_event(_trade(200), EngineContext(book2, om, now=200))  # must not raise

    # Two new orders created. Old sell got cancelled, old buy stays FILLED.
    assert len(om) == 4
    statuses = {o.status for o in (om.get(i) for i in range(1, 5))}
    assert OrderStatus.FILLED in statuses
    assert OrderStatus.CANCELLED in statuses
    assert sum(1 for _ in om.active()) == 2


# =========================================================================
# Integration: market-maker over real sample
# =========================================================================


def test_mm_on_real_sample_produces_non_empty_fills() -> None:
    """M6 done-when: engine + MM on the sample produces > 0 fills."""
    om = OrderManager()
    mm = NaiveMarketMaker(half_spread=0.0, size=100.0)
    events = EventStream(LobLoader(SAMPLE_LOB), TradesLoader(SAMPLE_TRADES))
    fills = Backtest(events, OrderBook(), om, MatchingEngine(), strategy=mm).run()
    assert len(fills) > 0
