"""The backtest driver — wires event stream → book + matcher → fills log.

Per-event order of operations:

    1. If event is a `LobSnapshot`, apply it to the book.
    2. Run the matcher against the event:
         - `LobSnapshot` -> `matcher.on_quote(book, active_orders)`
         - `Trade`       -> `matcher.on_trade(event, active_orders)`
    3. Append any resulting fills to the log.

There is no strategy hook in M5 — orders must be pre-seeded in the
`OrderManager` before `run()`. M6 introduces a `Strategy` callback that
fires after step 3 so strategies can react to the event and any fills it
produced.

The active-order list is snapshotted before each match call so that
mutations during fill emission (status -> FILLED) cannot interfere with
iteration.
"""

from __future__ import annotations

from collections.abc import Iterable

from hft_backtest.data.events import LobSnapshot, MarketEvent
from hft_backtest.execution.fill import Fill
from hft_backtest.execution.matcher import MatchingEngine
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders.manager import OrderManager


class Backtest:
    """One-shot backtest driver. Build, then call `run()` once."""

    __slots__ = ("_events", "_book", "_om", "_matcher")

    def __init__(
        self,
        events: Iterable[MarketEvent],
        book: OrderBook,
        order_manager: OrderManager,
        matcher: MatchingEngine,
    ) -> None:
        self._events = events
        self._book = book
        self._om = order_manager
        self._matcher = matcher

    def run(self) -> list[Fill]:
        fills_log: list[Fill] = []
        for event in self._events:
            if isinstance(event, LobSnapshot):
                self._book.apply(event)
                fills = self._matcher.on_quote(self._book, list(self._om.active()))
            else:
                fills = self._matcher.on_trade(event, list(self._om.active()))
            fills_log.extend(fills)
        return fills_log
