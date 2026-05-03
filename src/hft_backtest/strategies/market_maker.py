"""A naive symmetric market-maker.

Posts a buy at `mid - half_spread` and a sell at `mid + half_spread`,
each of size `size`. On each event, it inspects the book; if the mid
has moved by more than `repost_threshold` (default 0.0 — any change
triggers re-quote), it cancels the previous quotes and posts fresh.

Known limitations of the naive version (intentional, see TASKS M6):
  - If one side fills while the mid stays steady, that side stays
    one-sided until the next mid move triggers a repost.
  - No inventory awareness: quotes are symmetric regardless of
    accumulated position.
  - No size scaling, no skewing, no cancel-on-tilt.

These are deliberately out of scope; M11 may revisit.
"""

from hft_backtest.data.events import MarketEvent, Side
from hft_backtest.engine.context import EngineContext
from hft_backtest.orders.manager import OrderAlreadyDoneError
from hft_backtest.strategies.base import Strategy
from hft_backtest.strategies.registry import register


@register("market_maker")
class NaiveMarketMaker(Strategy):
    __slots__ = (
        "_half_spread",
        "_size",
        "_repost_threshold",
        "_buy_id",
        "_sell_id",
        "_last_quoted_mid",
    )

    def __init__(
        self,
        half_spread: float,
        size: float,
        repost_threshold: float = 0.0,
    ) -> None:
        if half_spread < 0:
            raise ValueError(f"half_spread must be >= 0, got {half_spread}")
        if size <= 0:
            raise ValueError(f"size must be > 0, got {size}")
        if repost_threshold < 0:
            raise ValueError(
                f"repost_threshold must be >= 0, got {repost_threshold}"
            )
        self._half_spread = half_spread
        self._size = size
        self._repost_threshold = repost_threshold
        self._buy_id: int | None = None
        self._sell_id: int | None = None
        self._last_quoted_mid: float | None = None

    def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:
        mid = ctx.book.mid()
        if mid is None:
            return

        if (
            self._last_quoted_mid is not None
            and abs(mid - self._last_quoted_mid) <= self._repost_threshold
        ):
            return

        self._cancel_safely(ctx)
        self._buy_id = ctx.place(Side.BUY, mid - self._half_spread, self._size).id
        self._sell_id = ctx.place(Side.SELL, mid + self._half_spread, self._size).id
        self._last_quoted_mid = mid

    def _cancel_safely(self, ctx: EngineContext) -> None:
        for attr in ("_buy_id", "_sell_id"):
            oid: int | None = getattr(self, attr)
            if oid is None:
                continue
            try:
                ctx.cancel(oid)
            except OrderAlreadyDoneError:
                pass  # already filled — nothing to cancel
            setattr(self, attr, None)
