"""L2 order book — pure market state, mirrored from snapshots.

The book holds no client orders and performs no matching. Each `apply` call
replaces state wholesale; the book is a thin reflection of the most recent
snapshot. Validation of source invariants (sorted levels, non-crossed,
non-negative sizes) is the loader's job — `apply` trusts its input.
"""

from __future__ import annotations

from hft_backtest.data.events import Level, LobSnapshot


class OrderBook:
    """L2 order book reconstructed from snapshot updates."""

    __slots__ = ("_bids", "_asks", "_timestamp")

    def __init__(self) -> None:
        self._bids: tuple[Level, ...] = ()
        self._asks: tuple[Level, ...] = ()
        self._timestamp: int | None = None

    def apply(self, snapshot: LobSnapshot) -> None:
        """Replace book state with `snapshot`."""
        self._bids = snapshot.bids
        self._asks = snapshot.asks
        self._timestamp = snapshot.timestamp

    @property
    def bids(self) -> tuple[Level, ...]:
        return self._bids

    @property
    def asks(self) -> tuple[Level, ...]:
        return self._asks

    @property
    def timestamp(self) -> int | None:
        return self._timestamp

    def best_bid(self) -> Level | None:
        return self._bids[0] if self._bids else None

    def best_ask(self) -> Level | None:
        return self._asks[0] if self._asks else None

    def mid(self) -> float | None:
        if not self._bids or not self._asks:
            return None
        return (self._bids[0].price + self._asks[0].price) / 2.0

    def spread(self) -> float | None:
        if not self._bids or not self._asks:
            return None
        return self._asks[0].price - self._bids[0].price
