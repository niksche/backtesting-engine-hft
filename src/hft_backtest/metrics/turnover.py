"""Cumulative turnover (notional traded) tracking."""

from __future__ import annotations

from hft_backtest.execution.fill import Fill


class TurnoverTracker:
    """Accumulates total notional value traded and fill count."""

    __slots__ = ("_total_notional", "_fill_count")

    def __init__(self) -> None:
        self._total_notional: float = 0.0
        self._fill_count: int = 0

    @property
    def total_notional(self) -> float:
        return self._total_notional

    @property
    def fill_count(self) -> int:
        return self._fill_count

    def on_fill(self, fill: Fill) -> None:
        """Add fill's notional value to the running total."""
        self._total_notional += fill.price * fill.size
        self._fill_count += 1
