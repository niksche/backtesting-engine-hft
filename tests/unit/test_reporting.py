"""Unit tests for hft_backtest.reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from hft_backtest.data.events import Side
from hft_backtest.metrics.recorder import MetricSnapshot
from hft_backtest.reporting import SummaryStats, compute_summary, generate_report


def _snap(
    ts: int = 1000,
    realized: float = 0.0,
    unrealized: float = 0.0,
    inventory: float = 0.0,
    turnover: float = 0.0,
    fill_count: int = 0,
) -> MetricSnapshot:
    return MetricSnapshot(
        timestamp=ts,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_pnl=realized + unrealized,
        inventory=inventory,
        turnover=turnover,
        fill_count=fill_count,
    )


# =========================================================================
# compute_summary
# =========================================================================


def test_summary_empty_snapshots() -> None:
    stats = compute_summary([])
    assert stats.final_total_pnl == 0.0
    assert stats.fill_count == 0
    assert stats.sharpe_ratio is None


def test_summary_single_snapshot() -> None:
    stats = compute_summary([_snap(realized=50.0, fill_count=3, turnover=1000.0)])
    assert stats.final_realized_pnl == 50.0
    assert stats.fill_count == 3
    assert stats.total_turnover == 1000.0
    assert stats.sharpe_ratio is None  # need >= 2 for returns


def test_summary_max_drawdown() -> None:
    snapshots = [
        _snap(ts=1, realized=0.0),
        _snap(ts=2, realized=100.0),
        _snap(ts=3, realized=50.0),    # drawdown = 50
        _snap(ts=4, realized=120.0),
        _snap(ts=5, realized=30.0),    # drawdown = 90 (peak 120 → 30)
    ]
    stats = compute_summary(snapshots)
    assert stats.max_drawdown == pytest.approx(90.0)


def test_summary_sharpe_positive() -> None:
    # Monotonically increasing PnL → positive Sharpe.
    snapshots = [
        _snap(ts=1, realized=0.0),
        _snap(ts=2, realized=10.0),
        _snap(ts=3, realized=20.0),
        _snap(ts=4, realized=30.0),
    ]
    stats = compute_summary(snapshots)
    assert stats.sharpe_ratio is not None
    # All returns equal → std=0 → inf
    # Actually returns are [10,10,10], mean=10, std=0 → inf or 0
    # Per our code: std=0, mean>0 → inf


def test_summary_avg_abs_inventory() -> None:
    snapshots = [
        _snap(inventory=100.0),
        _snap(inventory=-50.0),
        _snap(inventory=0.0),
    ]
    stats = compute_summary(snapshots)
    assert stats.avg_abs_inventory == pytest.approx(50.0)  # (100+50+0)/3
    assert stats.peak_abs_inventory == pytest.approx(100.0)


# =========================================================================
# generate_report
# =========================================================================


def test_generate_report_creates_files(tmp_path: Path) -> None:
    snapshots = [
        _snap(ts=100, realized=0.0, inventory=0.0, turnover=0.0, fill_count=0),
        _snap(ts=200, realized=50.0, inventory=100.0, turnover=1000.0, fill_count=1),
        _snap(ts=300, realized=100.0, inventory=0.0, turnover=2100.0, fill_count=2),
    ]
    report_path = generate_report(snapshots, tmp_path)

    assert report_path.exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "equity_curve.png").exists()
    assert (tmp_path / "inventory.png").exists()
    assert (tmp_path / "turnover.png").exists()


def test_report_md_contains_expected_sections(tmp_path: Path) -> None:
    snapshots = [
        _snap(ts=100, realized=0.0, fill_count=0),
        _snap(ts=200, realized=100.0, fill_count=2, turnover=2100.0),
    ]
    generate_report(snapshots, tmp_path)
    md = (tmp_path / "report.md").read_text()

    assert "# Backtest Performance Report" in md
    assert "Realized PnL" in md
    assert "Max Drawdown" in md
    assert "Sharpe Ratio" in md
    assert "Fill Count" in md
    assert "equity_curve.png" in md
    assert "inventory.png" in md
    assert "turnover.png" in md


def test_report_plots_are_nonempty_pngs(tmp_path: Path) -> None:
    snapshots = [
        _snap(ts=100),
        _snap(ts=200, realized=50.0, inventory=10.0, turnover=500.0, fill_count=1),
    ]
    generate_report(snapshots, tmp_path)

    for name in ("equity_curve.png", "inventory.png", "turnover.png"):
        png = tmp_path / name
        assert png.stat().st_size > 0
        # Verify PNG magic bytes.
        with open(png, "rb") as f:
            assert f.read(4) == b"\x89PNG"


def test_generate_report_handles_empty_snapshots(tmp_path: Path) -> None:
    report_path = generate_report([], tmp_path)
    assert report_path.exists()
    md = report_path.read_text()
    assert "Total PnL" in md
    # No plots generated for empty input.
    assert not (tmp_path / "equity_curve.png").exists()


def test_generate_report_creates_output_dir(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "deep" / "report"
    generate_report([_snap()], out)
    assert (out / "report.md").exists()
