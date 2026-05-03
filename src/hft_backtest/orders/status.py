"""Order lifecycle states."""

from __future__ import annotations

from enum import Enum


class OrderStatus(Enum):
    """Terminal states are FILLED and CANCELLED. PARTIALLY_FILLED is an
    intermediate state when partial fills are enabled.
    """

    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
