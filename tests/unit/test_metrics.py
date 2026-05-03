"""Unit tests for hft_backtest.metrics — PnL, inventory, turnover, recorder."""

from __future__ import annotations

from pathlib import Path

import pytest

from hft_backtest.data.event_stream import EventStream
from hft_backtest.data.events import Level, LobSnapshot, MarketEvent, Side, Trade
from hft_backtest.data.loaders import LobLoader, TradesLoader
from hft_backtest.engine import Backtest
from hft_backtest.execution.fill import Fill
from hft_backtest.execution.matcher import MatchingEngine
from hft_backtest.metrics import (
    InventoryTracker,
    MetricsRecorder,
    PnLTracker,
    TurnoverTracker,
)
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders import OrderManager
from hft_backtest.strategies import NaiveMarketMaker

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "samples"
SAMPLE_LOB = SAMPLE_DIR / "lob_sample.csv"
SAMPLE_TRADES = SAMPLE_DIR / "trades_sample.csv"


def _fill(
    order_id: int = 1,
    side: Side = Side.BUY,
    price: float = 10.0,
    size: float = 100.0,
    ts: int = 1000,
) -> Fill:
    return Fill(order_id=order_id, side=side, price=price, size=size, timestamp=ts)


# =========================================================================
# PnLTracker
# =========================================================================


def test_pnl_starts_at_zero() -> None:
    pnl = PnLTracker()
    assert pnl.realized_pnl == 0.0
    assert pnl.unrealized_pnl == 0.0
    assert pnl.total_pnl == 0.0
    assert pnl.position == 0.0


def test_pnl_buy_then_sell_at_profit() -> None:
    """TASKS.md hand-computed: buy 100 @ 10, sell 100 @ 11 → realized = 100."""
    pnl = PnLTracker()
    pnl.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0))
    assert pnl.position == 100.0
    assert pnl.avg_entry_price == 10.0
    assert pnl.realized_pnl == 0.0

    pnl.on_fill(_fill(side=Side.SELL, price=11.0, size=100.0))
    assert pnl.position == 0.0
    assert pnl.realized_pnl == pytest.approx(100.0)


def test_pnl_buy_then_sell_at_loss() -> None:
    pnl = PnLTracker()
    pnl.on_fill(_fill(side=Side.BUY, price=10.0, size=50.0))
    pnl.on_fill(_fill(side=Side.SELL, price=9.0, size=50.0))
    assert pnl.realized_pnl == pytest.approx(-50.0)
    assert pnl.position == 0.0


def test_pnl_short_then_cover() -> None:
    pnl = PnLTracker()
    pnl.on_fill(_fill(side=Side.SELL, price=10.0, size=100.0))
    assert pnl.position == -100.0

    pnl.on_fill(_fill(side=Side.BUY, price=9.0, size=100.0))
    assert pnl.realized_pnl == pytest.approx(100.0)
    assert pnl.position == 0.0


def test_pnl_adding_to_long_blends_avg_price() -> None:
    pnl = PnLTracker()
    pnl.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0))
    pnl.on_fill(_fill(side=Side.BUY, price=12.0, size=100.0))
    assert pnl.position == 200.0
    assert pnl.avg_entry_price == pytest.approx(11.0)
    assert pnl.realized_pnl == 0.0


def test_pnl_partial_close() -> None:
    pnl = PnLTracker()
    pnl.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0))
    pnl.on_fill(_fill(side=Side.SELL, price=12.0, size=50.0))
    assert pnl.position == 50.0
    assert pnl.realized_pnl == pytest.approx(100.0)  # 50 * (12 - 10)
    assert pnl.avg_entry_price == pytest.approx(10.0)


def test_pnl_flip_long_to_short() -> None:
    pnl = PnLTracker()
    pnl.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0))
    pnl.on_fill(_fill(side=Side.SELL, price=12.0, size=150.0))
    assert pnl.position == -50.0
    assert pnl.realized_pnl == pytest.approx(200.0)  # 100 * (12 - 10)
    assert pnl.avg_entry_price == pytest.approx(12.0)


def test_pnl_unrealized_tracks_mid() -> None:
    pnl = PnLTracker()
    pnl.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0))

    pnl.mark_to_market(11.0)
    assert pnl.unrealized_pnl == pytest.approx(100.0)  # 100 * (11 - 10)

    pnl.mark_to_market(9.0)
    assert pnl.unrealized_pnl == pytest.approx(-100.0)  # 100 * (9 - 10)


def test_pnl_unrealized_zero_when_flat() -> None:
    pnl = PnLTracker()
    pnl.mark_to_market(100.0)
    assert pnl.unrealized_pnl == 0.0


def test_pnl_unrealized_short() -> None:
    pnl = PnLTracker()
    pnl.on_fill(_fill(side=Side.SELL, price=10.0, size=100.0))
    pnl.mark_to_market(9.0)
    assert pnl.unrealized_pnl == pytest.approx(100.0)  # short @ 10, now 9 → profit

    pnl.mark_to_market(11.0)
    assert pnl.unrealized_pnl == pytest.approx(-100.0)  # loss


def test_pnl_total_is_sum() -> None:
    pnl = PnLTracker()
    pnl.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0))
    pnl.on_fill(_fill(side=Side.SELL, price=11.0, size=50.0))
    pnl.mark_to_market(12.0)
    assert pnl.total_pnl == pytest.approx(pnl.realized_pnl + pnl.unrealized_pnl)


# =========================================================================
# InventoryTracker
# =========================================================================


def test_inventory_starts_at_zero() -> None:
    inv = InventoryTracker()
    assert inv.position == 0.0
    assert inv.peak_long == 0.0
    assert inv.peak_short == 0.0


def test_inventory_buy_then_sell() -> None:
    inv = InventoryTracker()
    inv.on_fill(_fill(side=Side.BUY, size=100.0))
    assert inv.position == 100.0
    assert inv.peak_long == 100.0

    inv.on_fill(_fill(side=Side.SELL, size=100.0))
    assert inv.position == 0.0
    # peak_long should remain at 100
    assert inv.peak_long == 100.0


def test_inventory_tracks_peaks() -> None:
    inv = InventoryTracker()
    inv.on_fill(_fill(side=Side.BUY, size=50.0))
    inv.on_fill(_fill(side=Side.BUY, size=100.0))
    assert inv.peak_long == 150.0

    inv.on_fill(_fill(side=Side.SELL, size=200.0))
    assert inv.position == -50.0
    assert inv.peak_short == 50.0

    inv.on_fill(_fill(side=Side.SELL, size=100.0))
    assert inv.peak_short == 150.0
    assert inv.abs_peak == 150.0


def test_inventory_abs_peak() -> None:
    inv = InventoryTracker()
    inv.on_fill(_fill(side=Side.BUY, size=200.0))
    inv.on_fill(_fill(side=Side.SELL, size=300.0))
    assert inv.abs_peak == max(inv.peak_long, inv.peak_short)


# =========================================================================
# TurnoverTracker
# =========================================================================


def test_turnover_starts_at_zero() -> None:
    t = TurnoverTracker()
    assert t.total_notional == 0.0
    assert t.fill_count == 0


def test_turnover_hand_computed() -> None:
    """TASKS.md: buy 100 @ 10, sell 100 @ 11 → turnover = 2100."""
    t = TurnoverTracker()
    t.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0))
    t.on_fill(_fill(side=Side.SELL, price=11.0, size=100.0))
    assert t.total_notional == pytest.approx(2100.0)
    assert t.fill_count == 2


def test_turnover_accumulates() -> None:
    t = TurnoverTracker()
    t.on_fill(_fill(price=5.0, size=10.0))
    assert t.total_notional == pytest.approx(50.0)
    t.on_fill(_fill(price=6.0, size=20.0))
    assert t.total_notional == pytest.approx(170.0)
    assert t.fill_count == 2


# =========================================================================
# MetricsRecorder
# =========================================================================


def test_recorder_starts_with_no_snapshots() -> None:
    r = MetricsRecorder()
    assert r.snapshots == []


def test_recorder_on_fill_creates_snapshot() -> None:
    r = MetricsRecorder()
    r.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0, ts=1000), mid=10.0)
    assert len(r.snapshots) == 1
    snap = r.snapshots[0]
    assert snap.timestamp == 1000
    assert snap.inventory == 100.0
    assert snap.turnover == pytest.approx(1000.0)
    assert snap.fill_count == 1


def test_recorder_snapshot_marks_to_market() -> None:
    r = MetricsRecorder()
    r.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0, ts=1000), mid=10.0)
    r.snapshot(2000, mid=12.0)
    snap = r.snapshots[-1]
    assert snap.unrealized_pnl == pytest.approx(200.0)  # 100 * (12 - 10)
    assert snap.timestamp == 2000


def test_recorder_full_round_trip() -> None:
    """buy 100 @ 10, sell 100 @ 11 → realized 100, inventory 0, turnover 2100."""
    r = MetricsRecorder()
    r.on_fill(_fill(side=Side.BUY, price=10.0, size=100.0, ts=100), mid=10.0)
    r.on_fill(_fill(side=Side.SELL, price=11.0, size=100.0, ts=200), mid=11.0)
    r.snapshot(300, mid=11.0)

    final = r.snapshots[-1]
    assert final.realized_pnl == pytest.approx(100.0)
    assert final.unrealized_pnl == pytest.approx(0.0)
    assert final.inventory == 0.0
    assert final.turnover == pytest.approx(2100.0)
    assert final.fill_count == 2


# =========================================================================
# Engine integration — recorder wired into Backtest
# =========================================================================


def test_engine_with_recorder_collects_snapshots() -> None:
    om = OrderManager()
    om.place(Side.BUY, 100.0, 1.0, ts=0)
    events: list[MarketEvent] = [
        LobSnapshot(timestamp=100, bids=(Level(99.0, 1.0),), asks=(Level(101.0, 1.0),)),
        Trade(timestamp=200, side=Side.SELL, price=99.0, amount=1.0),
    ]
    recorder = MetricsRecorder()
    fills = Backtest(
        events, OrderBook(), om, MatchingEngine(), recorder=recorder
    ).run()
    assert len(fills) == 1
    # 1 fill snapshot + 1 final snapshot
    assert len(recorder.snapshots) >= 1


def test_engine_with_recorder_no_fills_still_gets_final_snapshot() -> None:
    events: list[MarketEvent] = [
        LobSnapshot(timestamp=100, bids=(Level(99.0, 1.0),), asks=(Level(101.0, 1.0),)),
    ]
    recorder = MetricsRecorder()
    Backtest(events, OrderBook(), OrderManager(), MatchingEngine(), recorder=recorder).run()
    # Final snapshot taken even with no fills
    assert len(recorder.snapshots) == 1
    assert recorder.snapshots[0].fill_count == 0


def test_engine_with_recorder_and_mm_on_sample() -> None:
    """End-to-end: MM on sample → coherent metrics series."""
    om = OrderManager()
    mm = NaiveMarketMaker(half_spread=0.0, size=100.0)
    recorder = MetricsRecorder()
    events = EventStream(LobLoader(SAMPLE_LOB), TradesLoader(SAMPLE_TRADES))
    fills = Backtest(
        events, OrderBook(), om, MatchingEngine(), strategy=mm, recorder=recorder
    ).run()
    assert len(fills) > 0
    assert len(recorder.snapshots) > 0

    # Timestamps should be non-decreasing.
    ts = [s.timestamp for s in recorder.snapshots]
    assert ts == sorted(ts)

    # Fill counts should be non-decreasing.
    counts = [s.fill_count for s in recorder.snapshots]
    assert counts == sorted(counts)

    # Turnover should be non-decreasing.
    turnovers = [s.turnover for s in recorder.snapshots]
    assert turnovers == sorted(turnovers)
