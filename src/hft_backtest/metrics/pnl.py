"""Realized and unrealized PnL tracking (average-cost method).

Position is tracked as a signed float (positive = long, negative = short).
When a fill reduces the absolute position (or flips it), the closed portion
is realized at the difference between fill price and average entry price.
The remainder (if any) starts a fresh cost basis at the fill price.
"""

from __future__ import annotations

from hft_backtest.data.events import Side
from hft_backtest.execution.fill import Fill


class PnLTracker:
    """Running PnL using average-cost accounting."""

    __slots__ = ("_position", "_avg_entry_price", "_realized_pnl", "_unrealized_pnl")

    def __init__(self) -> None:
        self._position: float = 0.0
        self._avg_entry_price: float = 0.0
        self._realized_pnl: float = 0.0
        self._unrealized_pnl: float = 0.0

    @property
    def position(self) -> float:
        return self._position

    @property
    def avg_entry_price(self) -> float:
        return self._avg_entry_price

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    @property
    def unrealized_pnl(self) -> float:
        return self._unrealized_pnl

    @property
    def total_pnl(self) -> float:
        return self._realized_pnl + self._unrealized_pnl

    def on_fill(self, fill: Fill) -> None:
        """Update position and realized PnL from a fill."""
        signed_qty = fill.size if fill.side is Side.BUY else -fill.size
        new_position = self._position + signed_qty

        if self._position == 0.0:
            # Opening from flat — no realization.
            self._avg_entry_price = fill.price
        elif _same_sign(self._position, signed_qty):
            # Adding to existing position — blend the average entry price.
            total_cost = self._avg_entry_price * abs(self._position) + fill.price * fill.size
            self._avg_entry_price = total_cost / abs(new_position)
        else:
            # Reducing or flipping position.
            closed_qty = min(abs(self._position), fill.size)
            if self._position > 0:
                # Was long, selling to close.
                self._realized_pnl += closed_qty * (fill.price - self._avg_entry_price)
            else:
                # Was short, buying to close.
                self._realized_pnl += closed_qty * (self._avg_entry_price - fill.price)

            if _same_sign(new_position, self._position) or new_position == 0.0:
                # Partially closed or went flat — avg entry unchanged.
                pass
            else:
                # Flipped through zero — remainder starts at fill price.
                self._avg_entry_price = fill.price

        self._position = new_position
        if self._position == 0.0:
            self._avg_entry_price = 0.0

    def mark_to_market(self, mid: float) -> None:
        """Update unrealized PnL given the current mid price."""
        if self._position == 0.0:
            self._unrealized_pnl = 0.0
        elif self._position > 0:
            self._unrealized_pnl = self._position * (mid - self._avg_entry_price)
        else:
            self._unrealized_pnl = abs(self._position) * (self._avg_entry_price - mid)


def _same_sign(a: float, b: float) -> bool:
    return (a > 0 and b > 0) or (a < 0 and b < 0)
