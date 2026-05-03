"""The backtest driver — wires event stream → book + matcher → strategy.

Per-event order of operations:

    1. If event is a ``LobSnapshot``, apply it to the book.
    2. Run the matcher against the event:
         - ``LobSnapshot`` → ``matcher.on_quote(book, active_orders)``
         - ``Trade``       → ``matcher.on_trade(event, active_orders)``
    3. Append any resulting fills to the log.
    4. If a recorder is attached, feed fills to the recorder.
    5. Build a context carrying this event's fills.
    6. For each fill: call ``strategy.on_fill(fill, ctx)``.
    7. Call ``strategy.on_event(event, ctx)``
       (which dispatches to ``on_snapshot`` / ``on_trade`` by default).
    8. Collect any market-order fills the strategy placed via ``ctx``,
       record them in metrics and the fill log.

Strategies react *after* matching, so limit orders placed in response to
event E are matched starting from event E+1 — correct latency semantics.
Market orders placed during the callback execute immediately within the
same event.
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
    """One-shot backtest driver. Build, then call ``run()`` once."""

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
            # 1. Update book / match.
            if isinstance(event, LobSnapshot):
                self._book.apply(event)
                fills = self._matcher.on_quote(self._book, list(self._om.active()))
            else:
                fills = self._matcher.on_trade(event, list(self._om.active()))
            fills_log.extend(fills)

            # 2. Record resting-order fills in metrics.
            if self._recorder is not None and fills:
                mid = self._book.mid()
                if mid is not None:
                    for fill in fills:
                        self._recorder.on_fill(fill, mid)

            # 3. Strategy callbacks.
            if self._strategy is not None:
                ctx = EngineContext(
                    self._book,
                    self._om,
                    event.timestamp,
                    fills=fills,
                    recorder=self._recorder,
                )

                # 3a. on_fill per fill (before on_event).
                for fill in fills:
                    self._strategy.on_fill(fill, ctx)

                # 3b. on_event (dispatches to on_snapshot / on_trade).
                self._strategy.on_event(event, ctx)

                # 3c. Collect market-order fills from ctx.
                market_fills = ctx.market_fills
                if market_fills:
                    fills_log.extend(market_fills)
                    if self._recorder is not None:
                        mid = self._book.mid()
                        if mid is not None:
                            for mf in market_fills:
                                self._recorder.on_fill(mf, mid)

            last_ts = event.timestamp

        # Final mark-to-market snapshot.
        if self._recorder is not None:
            mid = self._book.mid()
            if mid is not None:
                self._recorder.snapshot(last_ts, mid)

        return fills_log
