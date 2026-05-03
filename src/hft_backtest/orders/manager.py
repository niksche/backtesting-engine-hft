"""Order lifecycle bookkeeping. No matching logic lives here."""

from __future__ import annotations

from collections.abc import Iterator

from hft_backtest.data.events import Side
from hft_backtest.orders.order import Order
from hft_backtest.orders.status import OrderStatus


class UnknownOrderError(KeyError):
    """Raised when an operation references an order id that was never placed."""


class OrderAlreadyDoneError(RuntimeError):
    """Raised when cancelling an order whose status is already terminal."""


class OrderManager:
    """Issues monotonic IDs and tracks order lifecycle.

    The matching engine reads `active()` to decide fills and mutates
    `Order.status` / `filled_size` directly when fills happen — by design,
    so the manager stays bookkeeping-only.

    Cancelling an unknown id raises `UnknownOrderError`. Cancelling an
    order that is already FILLED or CANCELLED raises
    `OrderAlreadyDoneError` — silent no-ops mask strategy bugs.
    """

    __slots__ = ("_orders", "_next_id")

    def __init__(self) -> None:
        self._orders: dict[int, Order] = {}
        self._next_id: int = 1

    def place(self, side: Side, price: float, size: float, ts: int) -> Order:
        """Register a new resting order and return it."""
        if size <= 0:
            raise ValueError(f"size must be > 0, got {size}")
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")
        order = Order(id=self._next_id, side=side, price=price, size=size, ts=ts)
        self._orders[order.id] = order
        self._next_id += 1
        return order

    def cancel(self, order_id: int) -> Order:
        """Mark an active order CANCELLED. Returns the cancelled order."""
        order = self.get(order_id)
        if not order.is_active:
            raise OrderAlreadyDoneError(
                f"order {order_id} is {order.status.value}, cannot cancel"
            )
        order.status = OrderStatus.CANCELLED
        return order

    def get(self, order_id: int) -> Order:
        """Return the order with this id regardless of status."""
        try:
            return self._orders[order_id]
        except KeyError:
            raise UnknownOrderError(order_id) from None

    def active(self) -> Iterator[Order]:
        """Iterate orders with status NEW."""
        return (o for o in self._orders.values() if o.is_active)

    def __len__(self) -> int:
        """Total orders ever placed (regardless of current status)."""
        return len(self._orders)
