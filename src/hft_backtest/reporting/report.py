"""Performance report generation — Markdown + PNG plots.

Consumes a `MetricsRecorder`'s snapshot history and writes a report
directory containing:

  - `report.md`          — summary stats table
  - `equity_curve.png`   — total PnL over time
  - `inventory.png`      — signed inventory over time
  - `turnover.png`       — cumulative notional over time
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend — no GUI
import matplotlib.pyplot as plt  # noqa: E402

from hft_backtest.metrics.recorder import MetricSnapshot  # noqa: E402


@dataclass(frozen=True, slots=True)
class SummaryStats:
    """Computed summary statistics for the report header."""

    final_realized_pnl: float
    final_unrealized_pnl: float
    final_total_pnl: float
    max_drawdown: float
    sharpe_ratio: float | None  # None if insufficient data
    fill_count: int
    avg_abs_inventory: float
    peak_abs_inventory: float
    total_turnover: float


def compute_summary(snapshots: list[MetricSnapshot]) -> SummaryStats:
    """Derive summary stats from a metrics snapshot series."""
    if not snapshots:
        return SummaryStats(
            final_realized_pnl=0.0,
            final_unrealized_pnl=0.0,
            final_total_pnl=0.0,
            max_drawdown=0.0,
            sharpe_ratio=None,
            fill_count=0,
            avg_abs_inventory=0.0,
            peak_abs_inventory=0.0,
            total_turnover=0.0,
        )

    last = snapshots[-1]

    # Max drawdown: peak-to-trough of total PnL series.
    peak = -math.inf
    max_dd = 0.0
    for s in snapshots:
        if s.total_pnl > peak:
            peak = s.total_pnl
        dd = peak - s.total_pnl
        if dd > max_dd:
            max_dd = dd

    # Sharpe-like ratio on per-snapshot PnL changes.
    sharpe: float | None = None
    if len(snapshots) >= 2:
        returns = [
            snapshots[i].total_pnl - snapshots[i - 1].total_pnl
            for i in range(1, len(snapshots))
        ]
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(var_r)
        if std_r > 0:
            sharpe = mean_r / std_r
        else:
            sharpe = 0.0 if mean_r == 0 else math.inf

    # Average absolute inventory.
    avg_abs_inv = sum(abs(s.inventory) for s in snapshots) / len(snapshots)
    peak_abs_inv = max(abs(s.inventory) for s in snapshots)

    return SummaryStats(
        final_realized_pnl=last.realized_pnl,
        final_unrealized_pnl=last.unrealized_pnl,
        final_total_pnl=last.total_pnl,
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        fill_count=last.fill_count,
        avg_abs_inventory=avg_abs_inv,
        peak_abs_inventory=peak_abs_inv,
        total_turnover=last.turnover,
    )


def _write_markdown(output_dir: Path, stats: SummaryStats) -> Path:
    """Write the summary report as Markdown."""
    path = output_dir / "report.md"
    sharpe_str = f"{stats.sharpe_ratio:.4f}" if stats.sharpe_ratio is not None else "N/A"
    md = f"""# Backtest Performance Report

## Summary Statistics

| Metric | Value |
| ------ | ----- |
| Realized PnL | {stats.final_realized_pnl:,.4f} |
| Unrealized PnL | {stats.final_unrealized_pnl:,.4f} |
| **Total PnL** | **{stats.final_total_pnl:,.4f}** |
| Max Drawdown | {stats.max_drawdown:,.4f} |
| Sharpe Ratio (per-snapshot) | {sharpe_str} |
| Fill Count | {stats.fill_count:,} |
| Avg Abs Inventory | {stats.avg_abs_inventory:,.4f} |
| Peak Abs Inventory | {stats.peak_abs_inventory:,.4f} |
| Total Turnover | {stats.total_turnover:,.4f} |

## Charts

![Equity Curve](equity_curve.png)

![Inventory](inventory.png)

![Turnover](turnover.png)
"""
    path.write_text(md)
    return path


def _plot_series(
    timestamps: list[int],
    values: list[float],
    title: str,
    ylabel: str,
    output_path: Path,
    color: str = "#2196F3",
) -> None:
    """Render a simple time-series line chart and save as PNG."""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(timestamps, values, linewidth=0.8, color=color)
    ax.set_title(title, fontsize=12)
    ax.set_xlabel("Timestamp (µs)")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def generate_report(
    snapshots: list[MetricSnapshot],
    output_dir: str | Path,
) -> Path:
    """Generate a full performance report.

    Parameters
    ----------
    snapshots:
        Metric snapshot time series from a `MetricsRecorder`.
    output_dir:
        Directory to write `report.md` and PNG plots into.

    Returns
    -------
    Path to the written `report.md`.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = compute_summary(snapshots)
    report_path = _write_markdown(output_dir, stats)

    if snapshots:
        ts = [s.timestamp for s in snapshots]
        _plot_series(
            ts,
            [s.total_pnl for s in snapshots],
            "Equity Curve (Total PnL)",
            "PnL",
            output_dir / "equity_curve.png",
            color="#4CAF50",
        )
        _plot_series(
            ts,
            [s.inventory for s in snapshots],
            "Inventory (Signed Position)",
            "Position",
            output_dir / "inventory.png",
            color="#FF9800",
        )
        _plot_series(
            ts,
            [s.turnover for s in snapshots],
            "Cumulative Turnover",
            "Notional",
            output_dir / "turnover.png",
            color="#2196F3",
        )

    return report_path
