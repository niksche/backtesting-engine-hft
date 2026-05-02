"""Merge LOB snapshots and trades into one timestamp-ordered event stream."""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Iterator

from .events import LobSnapshot, MarketEvent, Trade


class EventStream:
    """Yield `MarketEvent`s in non-decreasing timestamp order.

    On tied timestamps, LOB snapshots are emitted before trades (this is
    `heapq.merge`'s stable ordering when `lob` is passed as the first
    iterable). Rationale: a quote update at time t reflects state the
    matching engine should see *before* processing trade prints at the
    same instant.
    """

    def __init__(
        self,
        lob: Iterable[LobSnapshot],
        trades: Iterable[Trade],
    ) -> None:
        self._lob = lob
        self._trades = trades

    def __iter__(self) -> Iterator[MarketEvent]:
        lob: Iterable[MarketEvent] = self._lob
        trades: Iterable[MarketEvent] = self._trades
        yield from heapq.merge(lob, trades, key=lambda e: e.timestamp)
