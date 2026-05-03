"""No-op strategy — does nothing on every event.

Used for plumbing tests (verify the engine pipeline works without any
strategy logic) and as a baseline (zero fills, zero PnL).
"""

from hft_backtest.strategies.base import Strategy
from hft_backtest.strategies.registry import register


@register("noop")
class NoopStrategy(Strategy):
    """A strategy that never places or cancels orders."""
