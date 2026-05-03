"""Signed inventory (position) tracking."""

from __future__ import annotations

from hft_backtest.data.events import Side
from hft_backtest.execution.fill import Fill


class InventoryTracker:
    """Tracks net signed position and peak statistics."""

    __slots__ = ("_position", "_peak_long", "_peak_short")

    def __init__(self) -> None:
        self._position: float = 0.0
        self._peak_long: float = 0.0
        self._peak_short: float = 0.0

    @property
    def position(self) -> float:
        return self._position

    @property
    def peak_long(self) -> float:
        """Largest positive position observed."""
        return self._peak_long

    @property
    def peak_short(self) -> float:
        """Largest negative position observed (as a positive number)."""
        return self._peak_short

    @property
    def abs_peak(self) -> float:
        """Largest absolute position ever held."""
        return max(self._peak_long, self._peak_short)

    def on_fill(self, fill: Fill) -> None:
        """Update position from a fill."""
        if fill.side is Side.BUY:
            self._position += fill.size
        else:
            self._position -= fill.size
        self._peak_long = max(self._peak_long, self._position)
        self._peak_short = max(self._peak_short, -self._position)
