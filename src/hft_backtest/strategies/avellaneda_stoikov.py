"""Avellaneda-Stoikov market-making strategy.

From "High-frequency trading in a limit order book" (Avellaneda & Stoikov, 2008).

The strategy quotes around a **reservation price** that skews away from
inventory risk, with an **optimal spread** that balances adverse selection
against fill probability.

Reservation price:
    r = s - q * gamma * sigma^2 * (T - t)

    where:
        s     = current mid price
        q     = signed inventory (positive = long)
        gamma = risk aversion parameter
        sigma = estimated volatility (rolling std of mid returns)
        T - t = time remaining in the trading session

Optimal spread:
    delta = gamma * sigma^2 * (T - t) + (2/gamma) * ln(1 + gamma/k)

    where:
        k = order arrival intensity parameter

Quote prices:
    bid = r - delta/2
    ask = r + delta/2

Parameters (all configurable via YAML):
    gamma            — risk aversion (higher → more inventory penalty)
    k                — order arrival intensity (higher → tighter spread)
    sigma_window     — number of mid-price observations for volatility estimate
    size             — quote size per side
    dt               — time remaining per event (set to 1.0 for infinite horizon)
    repost_threshold — minimum reservation price move to trigger re-quote
"""

import math
from collections import deque

from hft_backtest.data.events import LobSnapshot, Side, Trade
from hft_backtest.engine.context import EngineContext
from hft_backtest.execution.fill import Fill
from hft_backtest.orders.manager import OrderAlreadyDoneError
from hft_backtest.strategies.base import Strategy
from hft_backtest.strategies.registry import register


@register("avellaneda_stoikov")
class AvellanedaStoikov(Strategy):
    """Inventory-aware market-maker using the Avellaneda-Stoikov model."""

    __slots__ = (
        "_gamma",
        "_k",
        "_size",
        "_dt",
        "_repost_threshold",
        "_sigma_window",
        "_mid_history",
        "_k_window",
        "_trade_deltas",
        "_buy_id",
        "_sell_id",
        "_last_reservation",
        "_inventory",
    )

    def __init__(
        self,
        gamma: float = 0.1,
        k: float = 1.5,
        size: float = 100.0,
        dt: float = 1.0,
        sigma_window: float = 50.0,
        k_window: float = 50.0,
        repost_threshold: float = 0.0,
    ) -> None:
        if gamma <= 0:
            raise ValueError(f"gamma must be > 0, got {gamma}")
        if k <= 0:
            raise ValueError(f"k must be > 0, got {k}")
        if size <= 0:
            raise ValueError(f"size must be > 0, got {size}")
        self._gamma = gamma
        self._k = k
        self._size = size
        self._dt = dt
        self._sigma_window = int(sigma_window)
        self._k_window = int(k_window)
        self._repost_threshold = repost_threshold
        self._mid_history: deque[float] = deque(maxlen=self._sigma_window)
        self._trade_deltas: deque[float] = deque(maxlen=self._k_window)
        self._buy_id: int | None = None
        self._sell_id: int | None = None
        self._last_reservation: float | None = None
        self._inventory: float = 0.0

    def on_fill(self, fill: Fill, ctx: EngineContext) -> None:
        """Track inventory from fills."""
        if fill.side is Side.BUY:
            self._inventory += fill.size
        else:
            self._inventory -= fill.size

    def on_trade(self, trade: Trade, ctx: EngineContext) -> None:
        """Track trade distances from mid to estimate order arrival intensity k."""
        mid = ctx.book.mid()
        if mid is not None:
            delta = abs(trade.price - mid)
            self._trade_deltas.append(delta)

    def on_snapshot(self, snapshot: LobSnapshot, ctx: EngineContext) -> None:
        """Compute reservation price + optimal spread, then quote."""
        mid = ctx.book.mid()
        if mid is None:
            return

        self._mid_history.append(mid)

        # Need at least 2 observations to estimate sigma.
        if len(self._mid_history) < 2:
            return

        sigma = self._estimate_sigma()
        k_est = self._estimate_k()
        
        reservation = self._reservation_price(mid, self._inventory, sigma)
        spread = self._optimal_spread(sigma, k_est)

        # Only re-quote if reservation has moved enough.
        if (
            self._last_reservation is not None
            and abs(reservation - self._last_reservation) <= self._repost_threshold
        ):
            return

        self._cancel_safely(ctx)

        bid_price = reservation - spread / 2.0
        ask_price = reservation + spread / 2.0

        self._buy_id = ctx.place(Side.BUY, bid_price, self._size).id
        self._sell_id = ctx.place(Side.SELL, ask_price, self._size).id
        self._last_reservation = reservation

    def _reservation_price(self, mid: float, q: float, sigma: float) -> float:
        """r = s - q * gamma * sigma^2 * dt"""
        return mid - q * self._gamma * (sigma ** 2) * self._dt

    def _optimal_spread(self, sigma: float, k: float) -> float:
        """delta = gamma * sigma^2 * dt + (2/gamma) * ln(1 + gamma/k)"""
        inventory_component = self._gamma * (sigma ** 2) * self._dt
        arrival_component = (2.0 / self._gamma) * math.log(1.0 + self._gamma / k)
        return inventory_component + arrival_component

    def _estimate_k(self) -> float:
        """Maximum likelihood estimate of k = 1 / mean(delta)."""
        deltas = list(self._trade_deltas)
        if len(deltas) < 2:
            return self._k  # fallback to initial parameter
        
        mean_delta = sum(deltas) / len(deltas)
        if mean_delta <= 1e-12:
            return self._k
            
        return 1.0 / mean_delta

    def _estimate_sigma(self) -> float:
        """Rolling standard deviation of absolute price changes (dS = sigma * dW)."""
        mids = list(self._mid_history)
        n = len(mids)
        if n < 2:
            return 0.0

        # Absolute price changes
        changes = [mids[i] - mids[i - 1] for i in range(1, n)]
        if not changes:
            return 0.0

        mean_c = sum(changes) / len(changes)
        var_c = sum((c - mean_c) ** 2 for c in changes) / len(changes)
        return math.sqrt(var_c)

    def _cancel_safely(self, ctx: EngineContext) -> None:
        for attr in ("_buy_id", "_sell_id"):
            oid: int | None = getattr(self, attr)
            if oid is None:
                continue
            try:
                ctx.cancel(oid)
            except OrderAlreadyDoneError:
                pass
            setattr(self, attr, None)
