"""The `Fill` event emitted by the matching engine."""

from __future__ import annotations

from dataclasses import dataclass

from hft_backtest.data.events import Side


@dataclass(frozen=True, slots=True)
class Fill:
    """A single fill against a resting order.

    `price` is the resting order's limit price (we do not model price
    improvement). `timestamp` is the event time that caused the fill —
    i.e., the trade-print or snapshot timestamp.
    """

    order_id: int
    side: Side
    price: float
    size: float
    timestamp: int
