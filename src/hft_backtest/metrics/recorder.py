"""Metrics recorder — aggregates PnL, inventory, and turnover into time series.

The recorder is wired into the backtest engine. After each fill and at the
end of the run, it snapshots the current metric state. This avoids
snapshotting on every single event (which could be millions of rows on
the full dataset) while still capturing every inflection point.
"""

from __future__ import annotations

from dataclasses import dataclass

from hft_backtest.execution.fill import Fill
from hft_backtest.metrics.inventory import InventoryTracker
from hft_backtest.metrics.pnl import PnLTracker
from hft_backtest.metrics.turnover import TurnoverTracker


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    """Point-in-time metrics state."""

    timestamp: int
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    inventory: float
    turnover: float
    fill_count: int


class MetricsRecorder:
    """Aggregates all metric trackers and records time-series snapshots.

    Usage from the engine:
        recorder.on_fill(fill, current_mid)  — after each fill
        recorder.snapshot(timestamp, mid)     — at end-of-run or periodically
    """

    __slots__ = ("_pnl", "_inventory", "_turnover", "_snapshots")

    def __init__(self) -> None:
        self._pnl = PnLTracker()
        self._inventory = InventoryTracker()
        self._turnover = TurnoverTracker()
        self._snapshots: list[MetricSnapshot] = []

    @property
    def pnl(self) -> PnLTracker:
        return self._pnl

    @property
    def inventory(self) -> InventoryTracker:
        return self._inventory

    @property
    def turnover(self) -> TurnoverTracker:
        return self._turnover

    @property
    def snapshots(self) -> list[MetricSnapshot]:
        return self._snapshots

    def on_fill(self, fill: Fill, mid: float) -> None:
        """Process a fill through all trackers and record a snapshot."""
        self._pnl.on_fill(fill)
        self._pnl.mark_to_market(mid)
        self._inventory.on_fill(fill)
        self._turnover.on_fill(fill)
        self._snapshots.append(self._take_snapshot(fill.timestamp))

    def snapshot(self, timestamp: int, mid: float) -> None:
        """Record a mark-to-market snapshot without a fill."""
        self._pnl.mark_to_market(mid)
        self._snapshots.append(self._take_snapshot(timestamp))

    def _take_snapshot(self, timestamp: int) -> MetricSnapshot:
        return MetricSnapshot(
            timestamp=timestamp,
            realized_pnl=self._pnl.realized_pnl,
            unrealized_pnl=self._pnl.unrealized_pnl,
            total_pnl=self._pnl.total_pnl,
            inventory=self._inventory.position,
            turnover=self._turnover.total_notional,
            fill_count=self._turnover.fill_count,
        )
