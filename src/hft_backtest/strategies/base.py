"""Strategy base class with typed callbacks.

Override the callbacks you need:

- ``on_fill(fill, ctx)``       — one of your orders was filled
- ``on_snapshot(snapshot, ctx)`` — new L2 book update
- ``on_trade(trade, ctx)``     — new trade print from the tape
- ``on_event(event, ctx)``     — catch-all (dispatches to the above by default)

The engine calls them in this order per event:

    1. on_fill (once per fill from this event)
    2. on_event → on_snapshot / on_trade

All callbacks are no-ops by default. ``Strategy()`` works as a noop
placeholder.
"""

from __future__ import annotations

from hft_backtest.data.events import LobSnapshot, MarketEvent, Trade
from hft_backtest.engine.context import EngineContext
from hft_backtest.execution.fill import Fill


class Strategy:

    def on_fill(self, fill: Fill, ctx: EngineContext) -> None:  # noqa: B027
        """Called once per fill on our resting orders, before on_event.

        Use this to update inventory tracking, adjust signals, or
        immediately react to a fill (e.g., place a hedge).
        """

    def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:
        """Called once per market event, after fills are delivered.

        The default implementation dispatches to ``on_snapshot`` or
        ``on_trade``. Override this for a single catch-all handler,
        or override the typed methods for cleaner separation.
        """
        if isinstance(event, LobSnapshot):
            self.on_snapshot(event, ctx)
        elif isinstance(event, Trade):
            self.on_trade(event, ctx)

    def on_snapshot(self, snapshot: LobSnapshot, ctx: EngineContext) -> None:  # noqa: B027
        """Called on each L2 book snapshot update."""

    def on_trade(self, trade: Trade, ctx: EngineContext) -> None:  # noqa: B027
        """Called on each trade print from the tape."""
