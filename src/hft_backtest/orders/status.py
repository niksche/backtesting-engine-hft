"""Order lifecycle states."""

from __future__ import annotations

from enum import Enum


class OrderStatus(Enum):
    """Terminal states are FILLED and CANCELLED. PARTIALLY_FILLED arrives
    in M11 when partial fills are turned on.
    """

    NEW = "new"
    FILLED = "filled"
    CANCELLED = "cancelled"
