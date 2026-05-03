"""The `Order` dataclass.

Order identity (`id`, `side`, `price`, `size`, `ts`) is conceptually
immutable after placement; only `status` and `filled_size` change. We use
a regular (non-frozen) dataclass so the matching engine can mutate those
two fields directly without rebuilding the order each fill.
"""

from __future__ import annotations

from dataclasses import dataclass

from hft_backtest.data.events import Side
from hft_backtest.orders.status import OrderStatus


@dataclass(slots=True)
class Order:
    id: int
    side: Side
    price: float
    size: float
    ts: int  # placement timestamp, microseconds since epoch
    status: OrderStatus = OrderStatus.NEW
    filled_size: float = 0.0

    @property
    def is_active(self) -> bool:
        return self.status is OrderStatus.NEW

    @property
    def remaining_size(self) -> float:
        return self.size - self.filled_size
