"""Strategy base class.

Subclass and override `on_event` to react to market events. The default
implementation is a no-op so `Strategy()` works as a placeholder in
plumbing tests and quick experiments.
"""

from __future__ import annotations

from hft_backtest.data.events import MarketEvent
from hft_backtest.engine.context import EngineContext


class Strategy:
    def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:  # noqa: B027
        """Called once per market event, after matching.

        `event` is the raw event just dispatched. `ctx` exposes current
        book state, the event's timestamp, and `place` / `cancel` to
        manage the strategy's resting orders.
        """
