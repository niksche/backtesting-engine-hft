"""The backtest driver — wires event stream → book + matcher → strategy.

Per-event order of operations:

    1. If event is a `LobSnapshot`, apply it to the book.
    2. Run the matcher against the event:
         - `LobSnapshot` -> `matcher.on_quote(book, active_orders)`
         - `Trade`       -> `matcher.on_trade(event, active_orders)`
    3. Append any resulting fills to the log.
    4. If a recorder is attached, feed fills and mark-to-market snapshots.
    5. If a strategy is attached, call `strategy.on_event(event, ctx)`.

Strategies react *after* matching, so orders they place in response to
event E are matched starting from event E+1 — correct latency semantics
(you can't trade against information you haven't seen yet).

The active-order list is snapshotted before each match call so that
mutations during fill emission (status -> FILLED) cannot interfere with
iteration.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from hft_backtest.data.events import LobSnapshot, MarketEvent
from hft_backtest.engine.context import EngineContext
from hft_backtest.execution.fill import Fill
from hft_backtest.execution.matcher import MatchingEngine
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders.manager import OrderManager

if TYPE_CHECKING:
    from hft_backtest.metrics.recorder import MetricsRecorder
    from hft_backtest.strategies.base import Strategy


class Backtest:
    """One-shot backtest driver. Build, then call `run()` once."""

    __slots__ = ("_events", "_book", "_om", "_matcher", "_strategy", "_recorder")

    def __init__(
        self,
        events: Iterable[MarketEvent],
        book: OrderBook,
        order_manager: OrderManager,
        matcher: MatchingEngine,
        strategy: Strategy | None = None,
        recorder: MetricsRecorder | None = None,
    ) -> None:
        self._events = events
        self._book = book
        self._om = order_manager
        self._matcher = matcher
        self._strategy = strategy
        self._recorder = recorder

    def run(self) -> list[Fill]:
        fills_log: list[Fill] = []
        last_ts: int = 0
        for event in self._events:
            if isinstance(event, LobSnapshot):
                self._book.apply(event)
                fills = self._matcher.on_quote(self._book, list(self._om.active()))
            else:
                fills = self._matcher.on_trade(event, list(self._om.active()))
            fills_log.extend(fills)

            if self._recorder is not None and fills:
                mid = self._book.mid()
                if mid is not None:
                    for fill in fills:
                        self._recorder.on_fill(fill, mid)

            if self._strategy is not None:
                ctx = EngineContext(self._book, self._om, event.timestamp)
                self._strategy.on_event(event, ctx)

            last_ts = event.timestamp

        # Final mark-to-market snapshot at end of run.
        if self._recorder is not None:
            mid = self._book.mid()
            if mid is not None:
                self._recorder.snapshot(last_ts, mid)

        return fills_log
