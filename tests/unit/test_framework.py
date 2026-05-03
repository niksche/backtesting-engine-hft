"""Tests for the enhanced strategy framework — new context methods,
typed callbacks, market orders, and plugin registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hft_backtest.data.event_stream import EventStream
from hft_backtest.data.events import Level, LobSnapshot, MarketEvent, Side, Trade
from hft_backtest.data.loaders import LobLoader, TradesLoader
from hft_backtest.engine import Backtest, EngineContext
from hft_backtest.execution.fill import Fill
from hft_backtest.execution.matcher import MatchingEngine
from hft_backtest.metrics import MetricsRecorder
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders import OrderManager, OrderStatus
from hft_backtest.strategies import Strategy, build_strategy, registered_names
from hft_backtest.strategies.registry import _REGISTRY

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "samples"
SAMPLE_LOB = SAMPLE_DIR / "lob_sample.csv"
SAMPLE_TRADES = SAMPLE_DIR / "trades_sample.csv"


def _snap(bid: float = 99.0, ask: float = 101.0, ts: int = 1000) -> LobSnapshot:
    return LobSnapshot(
        timestamp=ts,
        bids=(Level(bid, 10.0),),
        asks=(Level(ask, 10.0),),
    )


def _ctx(
    bid: float = 99.0,
    ask: float = 101.0,
    now: int = 1000,
    fills: list[Fill] | None = None,
    recorder: MetricsRecorder | None = None,
) -> tuple[EngineContext, OrderManager]:
    book = OrderBook()
    book.apply(_snap(bid, ask, now))
    om = OrderManager()
    return EngineContext(book, om, now, fills=fills, recorder=recorder), om


# =========================================================================
# ctx.fills — fills from current event
# =========================================================================


def test_ctx_fills_empty_by_default() -> None:
    ctx, _ = _ctx()
    assert ctx.fills == []


def test_ctx_fills_carries_event_fills() -> None:
    fill = Fill(order_id=1, side=Side.BUY, price=99.0, size=1.0, timestamp=1000)
    ctx, _ = _ctx(fills=[fill])
    assert ctx.fills == [fill]
    assert len(ctx.fills) == 1


# =========================================================================
# ctx.get_order / ctx.active_orders / ctx.cancel_all
# =========================================================================


def test_ctx_get_order() -> None:
    ctx, _ = _ctx()
    o = ctx.place(Side.BUY, 99.0, 1.0)
    assert ctx.get_order(o.id) is o


def test_ctx_active_orders() -> None:
    ctx, _ = _ctx()
    o1 = ctx.place(Side.BUY, 99.0, 1.0)
    o2 = ctx.place(Side.SELL, 101.0, 1.0)
    active = ctx.active_orders
    assert {o.id for o in active} == {o1.id, o2.id}


def test_ctx_active_orders_excludes_cancelled() -> None:
    ctx, _ = _ctx()
    o1 = ctx.place(Side.BUY, 99.0, 1.0)
    o2 = ctx.place(Side.SELL, 101.0, 1.0)
    ctx.cancel(o1.id)
    active = ctx.active_orders
    assert [o.id for o in active] == [o2.id]


def test_ctx_cancel_all() -> None:
    ctx, _ = _ctx()
    ctx.place(Side.BUY, 99.0, 1.0)
    ctx.place(Side.SELL, 101.0, 1.0)
    ctx.place(Side.BUY, 98.0, 1.0)
    cancelled = ctx.cancel_all()
    assert len(cancelled) == 3
    assert ctx.active_orders == []


def test_ctx_cancel_all_skips_already_done() -> None:
    ctx, _ = _ctx()
    o1 = ctx.place(Side.BUY, 99.0, 1.0)
    ctx.place(Side.SELL, 101.0, 1.0)
    ctx.cancel(o1.id)  # already cancelled
    cancelled = ctx.cancel_all()
    assert len(cancelled) == 1  # only the sell


# =========================================================================
# ctx.market_buy / ctx.market_sell
# =========================================================================


def test_market_buy_fills_at_best_ask() -> None:
    ctx, om = _ctx(ask=101.5)
    fill = ctx.market_buy(5.0)
    assert fill is not None
    assert fill.side is Side.BUY
    assert fill.price == 101.5
    assert fill.size == 5.0
    assert fill.timestamp == ctx.now


def test_market_sell_fills_at_best_bid() -> None:
    ctx, om = _ctx(bid=99.5)
    fill = ctx.market_sell(3.0)
    assert fill is not None
    assert fill.side is Side.SELL
    assert fill.price == 99.5
    assert fill.size == 3.0


def test_market_buy_returns_none_without_liquidity() -> None:
    book = OrderBook()
    book.apply(LobSnapshot(timestamp=1000, bids=(Level(99.0, 10.0),), asks=()))
    om = OrderManager()
    ctx = EngineContext(book, om, 1000)
    assert ctx.market_buy(1.0) is None


def test_market_sell_returns_none_without_liquidity() -> None:
    book = OrderBook()
    book.apply(LobSnapshot(timestamp=1000, bids=(), asks=(Level(101.0, 10.0),)))
    om = OrderManager()
    ctx = EngineContext(book, om, 1000)
    assert ctx.market_sell(1.0) is None


def test_market_order_is_in_market_fills() -> None:
    ctx, _ = _ctx()
    fill = ctx.market_buy(1.0)
    assert fill in ctx.market_fills


def test_market_order_creates_filled_order_in_manager() -> None:
    ctx, om = _ctx()
    fill = ctx.market_buy(5.0)
    assert fill is not None
    order = om.get(fill.order_id)
    assert order.status is OrderStatus.FILLED
    assert order.filled_size == 5.0


# =========================================================================
# ctx.position / ctx.realized_pnl / ctx.total_pnl
# =========================================================================


def test_ctx_position_without_recorder_is_zero() -> None:
    ctx, _ = _ctx()
    assert ctx.position == 0.0
    assert ctx.realized_pnl == 0.0
    assert ctx.unrealized_pnl == 0.0
    assert ctx.total_pnl == 0.0


def test_ctx_position_reflects_recorder_state() -> None:
    recorder = MetricsRecorder()
    fill = Fill(order_id=1, side=Side.BUY, price=100.0, size=50.0, timestamp=1000)
    recorder.on_fill(fill, mid=100.0)

    ctx, _ = _ctx(recorder=recorder)
    assert ctx.position == 50.0
    assert ctx.realized_pnl == 0.0


def test_ctx_pnl_after_round_trip() -> None:
    recorder = MetricsRecorder()
    recorder.on_fill(
        Fill(order_id=1, side=Side.BUY, price=10.0, size=100.0, timestamp=100),
        mid=10.0,
    )
    recorder.on_fill(
        Fill(order_id=2, side=Side.SELL, price=11.0, size=100.0, timestamp=200),
        mid=11.0,
    )
    ctx, _ = _ctx(recorder=recorder)
    assert ctx.position == 0.0
    assert ctx.realized_pnl == pytest.approx(100.0)


# =========================================================================
# on_fill callback
# =========================================================================


class _FillTracker(Strategy):
    def __init__(self) -> None:
        self.received_fills: list[Fill] = []

    def on_fill(self, fill: Fill, ctx: EngineContext) -> None:
        self.received_fills.append(fill)


def test_on_fill_fires_for_each_fill() -> None:
    tracker = _FillTracker()
    om = OrderManager()
    om.place(Side.BUY, 100.0, 1.0, ts=0)
    om.place(Side.SELL, 110.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        Trade(timestamp=100, side=Side.BUY, price=110.0, amount=1.0),  # fills sell
        Trade(timestamp=200, side=Side.SELL, price=100.0, amount=1.0),  # fills buy
    ]
    Backtest(events, OrderBook(), om, MatchingEngine(), strategy=tracker).run()
    assert len(tracker.received_fills) == 2
    assert tracker.received_fills[0].timestamp == 100
    assert tracker.received_fills[1].timestamp == 200


def test_on_fill_fires_before_on_event() -> None:
    """on_fill should fire before on_event so strategy can update state."""
    call_order: list[str] = []

    class Ordered(Strategy):
        def on_fill(self, fill: Fill, ctx: EngineContext) -> None:
            call_order.append("fill")

        def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:
            call_order.append("event")

    om = OrderManager()
    om.place(Side.BUY, 100.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        Trade(timestamp=100, side=Side.SELL, price=99.0, amount=1.0),
    ]
    Backtest(events, OrderBook(), om, MatchingEngine(), strategy=Ordered()).run()
    assert call_order == ["fill", "event"]


# =========================================================================
# on_snapshot / on_trade typed dispatch
# =========================================================================


class _TypedRecorder(Strategy):
    def __init__(self) -> None:
        self.snapshots: list[int] = []
        self.trades: list[int] = []

    def on_snapshot(self, snapshot: LobSnapshot, ctx: EngineContext) -> None:
        self.snapshots.append(snapshot.timestamp)

    def on_trade(self, trade: Trade, ctx: EngineContext) -> None:
        self.trades.append(trade.timestamp)


def test_typed_callbacks_dispatch() -> None:
    rec = _TypedRecorder()
    events: list[MarketEvent] = [
        LobSnapshot(timestamp=100, bids=(), asks=()),
        Trade(timestamp=200, side=Side.BUY, price=1.0, amount=1.0),
        LobSnapshot(timestamp=300, bids=(), asks=()),
    ]
    Backtest(events, OrderBook(), OrderManager(), MatchingEngine(), strategy=rec).run()
    assert rec.snapshots == [100, 300]
    assert rec.trades == [200]


def test_overriding_on_event_bypasses_typed_dispatch() -> None:
    """If you override on_event directly, on_snapshot/on_trade don't fire."""
    call_order: list[str] = []

    class DirectHandler(Strategy):
        def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:
            call_order.append("event")

        def on_snapshot(self, snapshot: LobSnapshot, ctx: EngineContext) -> None:
            call_order.append("snapshot")  # should NOT fire

    events: list[MarketEvent] = [LobSnapshot(timestamp=100, bids=(), asks=())]
    Backtest(events, OrderBook(), OrderManager(), MatchingEngine(), strategy=DirectHandler()).run()
    assert call_order == ["event"]


# =========================================================================
# ctx.fills available inside on_event
# =========================================================================


def test_ctx_fills_available_in_on_event() -> None:
    seen_fills: list[int] = []

    class FillInspector(Strategy):
        def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:
            seen_fills.extend(f.order_id for f in ctx.fills)

    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        Trade(timestamp=100, side=Side.SELL, price=99.0, amount=1.0),
    ]
    Backtest(events, OrderBook(), om, MatchingEngine(), strategy=FillInspector()).run()
    assert seen_fills == [o.id]


# =========================================================================
# Market orders through the engine
# =========================================================================


def test_engine_records_market_order_fills() -> None:
    class TakerStrategy(Strategy):
        def on_snapshot(self, snapshot: LobSnapshot, ctx: EngineContext) -> None:
            ctx.market_buy(1.0)

    events: list[MarketEvent] = [_snap(bid=99.0, ask=101.0, ts=100)]
    recorder = MetricsRecorder()
    fills = Backtest(
        events, OrderBook(), OrderManager(), MatchingEngine(),
        strategy=TakerStrategy(), recorder=recorder,
    ).run()
    assert len(fills) == 1
    assert fills[0].side is Side.BUY
    assert fills[0].price == 101.0


def test_engine_market_order_appears_in_fill_log() -> None:
    class BuySellTaker(Strategy):
        def on_snapshot(self, snapshot: LobSnapshot, ctx: EngineContext) -> None:
            ctx.market_buy(2.0)
            ctx.market_sell(3.0)

    events: list[MarketEvent] = [_snap(ts=100)]
    fills = Backtest(
        events, OrderBook(), OrderManager(), MatchingEngine(),
        strategy=BuySellTaker(),
    ).run()
    assert len(fills) == 2
    assert fills[0].side is Side.BUY
    assert fills[1].side is Side.SELL


# =========================================================================
# Strategy plugin registry
# =========================================================================


def test_registry_contains_builtins() -> None:
    names = registered_names()
    assert "noop" in names
    assert "market_maker" in names


def test_build_noop_strategy() -> None:
    s = build_strategy("noop", {})
    assert isinstance(s, Strategy)


def test_build_market_maker_strategy() -> None:
    s = build_strategy("market_maker", {"half_spread": 0.5, "size": 10.0})
    # Should not raise and should be the right type.
    from hft_backtest.strategies import NaiveMarketMaker
    assert isinstance(s, NaiveMarketMaker)


def test_build_unknown_strategy_raises() -> None:
    with pytest.raises(KeyError, match="unknown"):
        build_strategy("nonexistent", {})


# =========================================================================
# Full integration: complex strategy using all new features
# =========================================================================


class InventoryAwareMM(Strategy):
    """A test strategy that uses all new framework features."""

    def __init__(self) -> None:
        self.fill_count = 0
        self.max_inventory = 200.0

    def on_fill(self, fill: Fill, ctx: EngineContext) -> None:
        self.fill_count += 1

    def on_snapshot(self, snapshot: LobSnapshot, ctx: EngineContext) -> None:
        mid = ctx.book.mid()
        if mid is None:
            return

        # Cancel all stale orders.
        ctx.cancel_all()

        # Use position awareness to skew.
        pos = ctx.position

        # Post at the mid (half_spread=0) for guaranteed fills on sample.
        if pos < self.max_inventory:
            ctx.place(Side.BUY, mid, 100.0)
        if pos > -self.max_inventory:
            ctx.place(Side.SELL, mid, 100.0)

    def on_trade(self, trade: Trade, ctx: EngineContext) -> None:
        # On large trades, take liquidity to hedge.
        if abs(ctx.position) > self.max_inventory:
            if ctx.position > 0:
                ctx.market_sell(50.0)
            else:
                ctx.market_buy(50.0)


def test_complex_strategy_on_sample() -> None:
    """Full integration: inventory-aware MM on sample data."""
    om = OrderManager()
    recorder = MetricsRecorder()
    strategy = InventoryAwareMM()
    events = EventStream(LobLoader(SAMPLE_LOB), TradesLoader(SAMPLE_TRADES))
    fills = Backtest(
        events, OrderBook(), om, MatchingEngine(),
        strategy=strategy, recorder=recorder,
    ).run()
    # Should produce fills (both maker and taker).
    assert len(fills) > 0
    assert strategy.fill_count > 0
    assert len(recorder.snapshots) > 0
