"""Matching engine — decides which resting orders fill on each event.

Crossing rules
--------------

Trade prints (``on_trade``) — **inclusive** crossing with aggressor check:
    BUY  at P fills when trade.side == SELL and trade.price <= P.
    SELL at P fills when trade.side == BUY  and trade.price >= P.

Quote updates (``on_quote``) — **strict** crossing:
    BUY  at P fills when best_ask < P.
    SELL at P fills when best_bid > P.

Strict on quotes avoids spurious fills on the snapshot taken right after
placement, when the book is naturally at parity with our limit. Inclusive
on trades reflects the spec's "market price crosses the order level."

Fills are at the resting order's limit price (no price improvement). Each
fill mutates the order in place (status -> FILLED, filled_size updated).
Subsequent matching attempts skip the order via ``is_active``.

Partial fills
-------------

When ``partial_fills_enabled`` is True:

- **Trade-triggered fills**: fill size is ``min(order.remaining, trade.amount)``.
  The order stays active (PARTIALLY_FILLED) until remaining reaches zero.
  The trade's available amount is decremented as it fills multiple resting
  orders (price-time priority: orders are matched in iteration order).

- **Quote-triggered fills**: remain full-size (no volume info from a quote
  update). The order is fully filled in one step.
"""

from __future__ import annotations

from collections.abc import Iterable

from hft_backtest.data.events import Level, Side, Trade
from hft_backtest.execution.fill import Fill
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders.order import Order
from hft_backtest.orders.status import OrderStatus


class MatchingEngine:
    """Per-event matcher. Pure function of (event, resting orders) -> fills."""

    __slots__ = ("partial_fills_enabled",)

    def __init__(self, partial_fills_enabled: bool = False) -> None:
        self.partial_fills_enabled = partial_fills_enabled

    def on_trade(
        self, trade: Trade, resting_orders: Iterable[Order]
    ) -> list[Fill]:
        if not self.partial_fills_enabled:
            return [
                self._full_fill(o, trade.timestamp)
                for o in resting_orders
                if o.is_active and self._trade_crosses(trade, o)
            ]

        # Partial-fill mode: track remaining trade volume.
        fills: list[Fill] = []
        remaining_amount = trade.amount
        for o in resting_orders:
            if remaining_amount <= 0:
                break
            if not o.is_active or not self._trade_crosses(trade, o):
                continue
            fill_size = min(o.remaining_size, remaining_amount)
            fills.append(self._partial_fill(o, fill_size, trade.timestamp))
            remaining_amount -= fill_size
        return fills

    def on_quote(
        self, book: OrderBook, resting_orders: Iterable[Order]
    ) -> list[Fill]:
        if book.timestamp is None:
            return []
        bb = book.best_bid()
        ba = book.best_ask()
        ts = book.timestamp
        # Quote-triggered fills are always full-size (no volume info).
        return [
            self._full_fill(o, ts)
            for o in resting_orders
            if o.is_active and self._quote_crosses(bb, ba, o)
        ]

    @staticmethod
    def _trade_crosses(trade: Trade, order: Order) -> bool:
        if order.side is Side.BUY:
            return trade.side is Side.SELL and trade.price <= order.price
        return trade.side is Side.BUY and trade.price >= order.price

    @staticmethod
    def _quote_crosses(
        best_bid: Level | None, best_ask: Level | None, order: Order
    ) -> bool:
        if order.side is Side.BUY:
            return best_ask is not None and best_ask.price < order.price
        return best_bid is not None and best_bid.price > order.price

    def _full_fill(self, order: Order, timestamp: int) -> Fill:
        """Execute a full fill (the only mode when partial fills are off)."""
        fill_size = order.remaining_size
        order.filled_size = order.size
        order.status = OrderStatus.FILLED
        return Fill(
            order_id=order.id,
            side=order.side,
            price=order.price,
            size=fill_size,
            timestamp=timestamp,
        )

    def _partial_fill(self, order: Order, fill_size: float, timestamp: int) -> Fill:
        """Execute a partial (or completing) fill."""
        order.filled_size += fill_size
        if order.remaining_size <= 0:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        return Fill(
            order_id=order.id,
            side=order.side,
            price=order.price,
            size=fill_size,
            timestamp=timestamp,
        )
