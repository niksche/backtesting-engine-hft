"""Integration test: sample data + market-maker → deterministic metrics."""

from __future__ import annotations

from pathlib import Path

from hft_backtest.data.event_stream import EventStream
from hft_backtest.data.loaders import LobLoader, TradesLoader
from hft_backtest.engine import Backtest
from hft_backtest.execution.matcher import MatchingEngine
from hft_backtest.metrics import MetricsRecorder
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders import OrderManager
from hft_backtest.strategies import NaiveMarketMaker

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "samples"
SAMPLE_LOB = SAMPLE_DIR / "lob_sample.csv"
SAMPLE_TRADES = SAMPLE_DIR / "trades_sample.csv"


def _run_mm_backtest() -> MetricsRecorder:
    om = OrderManager()
    mm = NaiveMarketMaker(half_spread=0.0, size=100.0)
    recorder = MetricsRecorder()
    events = EventStream(LobLoader(SAMPLE_LOB), TradesLoader(SAMPLE_TRADES))
    Backtest(events, OrderBook(), om, MatchingEngine(), strategy=mm, recorder=recorder).run()
    return recorder


def test_end_to_end_determinism() -> None:
    """Same config + same sample → same metrics, byte-for-byte."""
    r1 = _run_mm_backtest()
    r2 = _run_mm_backtest()

    assert len(r1.snapshots) == len(r2.snapshots)
    for s1, s2 in zip(r1.snapshots, r2.snapshots):
        assert s1 == s2


def test_end_to_end_produces_fills_and_metrics() -> None:
    r = _run_mm_backtest()
    assert len(r.snapshots) > 0

    final = r.snapshots[-1]
    assert final.fill_count > 0
    assert final.turnover > 0


def test_end_to_end_report_generation(tmp_path: Path) -> None:
    """Full pipeline: sample → MM → report directory."""
    from hft_backtest.reporting import generate_report

    r = _run_mm_backtest()
    out = tmp_path / "report_output"
    report_path = generate_report(r.snapshots, out)

    assert report_path.exists()
    assert (out / "equity_curve.png").exists()
    assert (out / "inventory.png").exists()
    assert (out / "turnover.png").exists()

    md = report_path.read_text()
    assert "Total PnL" in md
    assert "Fill Count" in md
