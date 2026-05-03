"""Unit tests for hft_backtest.engine.backtest."""

from __future__ import annotations

from pathlib import Path

from hft_backtest.data.event_stream import EventStream
from hft_backtest.data.events import Level, LobSnapshot, MarketEvent, Side, Trade
from hft_backtest.data.loaders import LobLoader, TradesLoader
from hft_backtest.engine import Backtest
from hft_backtest.execution.fill import Fill
from hft_backtest.execution.matcher import MatchingEngine
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders import OrderManager, OrderStatus

SAMPLE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "data" / "samples"
)
SAMPLE_LOB = SAMPLE_DIR / "lob_sample.csv"
SAMPLE_TRADES = SAMPLE_DIR / "trades_sample.csv"


def _new_backtest(events: list[MarketEvent], om: OrderManager | None = None) -> Backtest:
    return Backtest(
        events=events,
        book=OrderBook(),
        order_manager=om if om is not None else OrderManager(),
        matcher=MatchingEngine(),
    )


# ---------- empty / pass-through ----------------------------------------


def test_run_empty_event_stream_returns_no_fills() -> None:
    bt = _new_backtest(events=[])
    assert bt.run() == []


def test_run_with_no_orders_yields_no_fills() -> None:
    events: list[MarketEvent] = [
        LobSnapshot(timestamp=100, bids=(Level(99.0, 1.0),), asks=(Level(101.0, 1.0),)),
        Trade(timestamp=200, side=Side.SELL, price=99.0, amount=1.0),
        Trade(timestamp=300, side=Side.BUY, price=101.0, amount=1.0),
    ]
    assert _new_backtest(events).run() == []


# ---------- book updating from snapshots --------------------------------


def test_run_applies_snapshots_to_book() -> None:
    book = OrderBook()
    snap = LobSnapshot(
        timestamp=500,
        bids=(Level(99.0, 5.0),),
        asks=(Level(101.0, 4.0),),
    )
    Backtest([snap], book, OrderManager(), MatchingEngine()).run()
    assert book.timestamp == 500
    assert book.best_bid() == Level(99.0, 5.0)
    assert book.best_ask() == Level(101.0, 4.0)


def test_run_does_not_apply_trades_to_book() -> None:
    """Trades don't change book state in M5 — only snapshots do."""
    book = OrderBook()
    events: list[MarketEvent] = [
        Trade(timestamp=100, side=Side.SELL, price=99.0, amount=1.0),
    ]
    Backtest(events, book, OrderManager(), MatchingEngine()).run()
    assert book.timestamp is None
    assert book.bids == ()
    assert book.asks == ()


# ---------- pre-seeded order fills --------------------------------------


def test_run_fills_pre_seeded_buy_on_crossing_trade() -> None:
    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        LobSnapshot(timestamp=100, bids=(Level(99.0, 1.0),), asks=(Level(101.0, 1.0),)),
        Trade(timestamp=200, side=Side.SELL, price=99.0, amount=1.0),
    ]
    fills = _new_backtest(events, om=om).run()
    assert len(fills) == 1
    assert fills[0].order_id == o.id
    assert fills[0].timestamp == 200
    assert o.status is OrderStatus.FILLED


def test_run_fills_pre_seeded_sell_on_crossing_trade() -> None:
    om = OrderManager()
    o = om.place(Side.SELL, 100.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        Trade(timestamp=200, side=Side.BUY, price=101.0, amount=1.0),
    ]
    fills = _new_backtest(events, om=om).run()
    assert len(fills) == 1
    assert fills[0].order_id == o.id


def test_run_fills_via_quote_when_book_crosses() -> None:
    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        LobSnapshot(timestamp=500, bids=(Level(99.0, 1.0),), asks=(Level(101.0, 1.0),)),
        LobSnapshot(timestamp=1000, bids=(Level(98.0, 1.0),), asks=(Level(99.5, 1.0),)),
    ]
    fills = _new_backtest(events, om=om).run()
    assert len(fills) == 1
    assert fills[0].order_id == o.id
    assert fills[0].timestamp == 1000


# ---------- ordering / multi-event --------------------------------------


def test_fills_logged_in_event_order() -> None:
    om = OrderManager()
    o_buy = om.place(Side.BUY, 100.0, 1.0, ts=0)
    o_sell = om.place(Side.SELL, 110.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        Trade(timestamp=100, side=Side.BUY, price=110.0, amount=1.0),  # fills sell
        Trade(timestamp=200, side=Side.SELL, price=100.0, amount=1.0),  # fills buy
    ]
    fills = _new_backtest(events, om=om).run()
    assert [f.order_id for f in fills] == [o_sell.id, o_buy.id]
    assert [f.timestamp for f in fills] == [100, 200]


def test_filled_orders_skipped_on_subsequent_events() -> None:
    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        Trade(timestamp=100, side=Side.SELL, price=99.0, amount=1.0),  # fills
        Trade(timestamp=200, side=Side.SELL, price=98.0, amount=1.0),  # would also cross
    ]
    fills = _new_backtest(events, om=om).run()
    assert len(fills) == 1
    assert fills[0].order_id == o.id


def test_event_stream_works_as_input() -> None:
    """Sanity: the engine accepts EventStream, not just a plain list."""
    om = OrderManager()
    om.place(Side.BUY, 100.0, 1.0, ts=0)
    lob = [LobSnapshot(timestamp=100, bids=(Level(99.0, 1.0),), asks=(Level(101.0, 1.0),))]
    trades = [Trade(timestamp=150, side=Side.SELL, price=99.0, amount=1.0)]
    stream = EventStream(lob, trades)
    fills = Backtest(stream, OrderBook(), om, MatchingEngine()).run()
    assert len(fills) == 1


# ---------- determinism --------------------------------------------------


def _scenario_run() -> list[Fill]:
    om = OrderManager()
    om.place(Side.BUY, 100.0, 1.0, ts=0)
    om.place(Side.SELL, 110.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        LobSnapshot(timestamp=100, bids=(Level(99.0, 1.0),), asks=(Level(101.0, 1.0),)),
        Trade(timestamp=200, side=Side.BUY, price=110.0, amount=1.0),
        Trade(timestamp=300, side=Side.SELL, price=100.0, amount=1.0),
    ]
    return Backtest(events, OrderBook(), om, MatchingEngine()).run()


def test_engine_is_deterministic() -> None:
    a = _scenario_run()
    b = _scenario_run()
    assert a == b
    assert len(a) == 2


# ---------- real sample replay ------------------------------------------


def test_engine_runs_over_real_sample_with_no_orders() -> None:
    """M5 done-when: engine runs over sample CSVs end-to-end → empty log."""
    events = EventStream(LobLoader(SAMPLE_LOB), TradesLoader(SAMPLE_TRADES))
    bt = Backtest(events, OrderBook(), OrderManager(), MatchingEngine())
    fills = bt.run()
    assert fills == []
