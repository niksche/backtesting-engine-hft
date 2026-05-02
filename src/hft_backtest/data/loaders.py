"""Streaming CSV loaders for L2 snapshots and trades."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from pathlib import Path
from typing import IO

from .events import Level, LobSnapshot, Side, Trade

_ASK_PRICE_RE = re.compile(r"^asks\[(\d+)\]\.price$")

Source = str | Path | IO[str]


class LobLoader:
    """Iterate `LobSnapshot`s row-by-row from an L2 CSV.

    Schema: leading unnamed index column, then `local_timestamp`, then
    `asks[i].price, asks[i].amount, bids[i].price, bids[i].amount` repeated
    per level. The number of levels is auto-detected from the header.
    """

    def __init__(self, source: Source) -> None:
        self._source = source

    def __iter__(self) -> Iterator[LobSnapshot]:
        if isinstance(self._source, (str, Path)):
            with open(self._source, newline="") as f:
                yield from self._iter_rows(f)
        else:
            yield from self._iter_rows(self._source)

    @staticmethod
    def _detect_levels(header: list[str]) -> int:
        levels = 0
        for col in header:
            m = _ASK_PRICE_RE.match(col)
            if m:
                levels = max(levels, int(m.group(1)) + 1)
        if levels == 0:
            raise ValueError("LOB header has no asks[i].price columns")
        return levels

    def _iter_rows(self, f: IO[str]) -> Iterator[LobSnapshot]:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return
        n_levels = self._detect_levels(header)
        for row in reader:
            ts = int(row[1])
            bids: list[Level] = []
            asks: list[Level] = []
            for i in range(n_levels):
                base = 2 + i * 4
                asks.append(Level(price=float(row[base]), amount=float(row[base + 1])))
                bids.append(Level(price=float(row[base + 2]), amount=float(row[base + 3])))
            yield LobSnapshot(timestamp=ts, bids=tuple(bids), asks=tuple(asks))


class TradesLoader:
    """Iterate `Trade`s row-by-row from a trades CSV.

    Schema: leading unnamed index column, then
    `local_timestamp, side, price, amount`.
    """

    def __init__(self, source: Source) -> None:
        self._source = source

    def __iter__(self) -> Iterator[Trade]:
        if isinstance(self._source, (str, Path)):
            with open(self._source, newline="") as f:
                yield from self._iter_rows(f)
        else:
            yield from self._iter_rows(self._source)

    def _iter_rows(self, f: IO[str]) -> Iterator[Trade]:
        reader = csv.reader(f)
        try:
            next(reader)  # header
        except StopIteration:
            return
        for row in reader:
            yield Trade(
                timestamp=int(row[1]),
                side=Side(row[2]),
                price=float(row[3]),
                amount=float(row[4]),
            )
