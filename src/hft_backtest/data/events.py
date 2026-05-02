"""Market event types — what loaders yield and the engine consumes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class Level:
    """One price level in the L2 book."""

    price: float
    amount: float


@dataclass(frozen=True, slots=True)
class LobSnapshot:
    """An L2 order book snapshot at a single timestamp.

    `bids` and `asks` are ordered by aggressiveness: index 0 is the best
    price (highest bid / lowest ask). Both tuples have the same length.
    """

    timestamp: int  # microseconds since Unix epoch
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]


@dataclass(frozen=True, slots=True)
class Trade:
    """A single trade print from the tape."""

    timestamp: int  # microseconds since Unix epoch
    side: Side
    price: float
    amount: float


MarketEvent = LobSnapshot | Trade
