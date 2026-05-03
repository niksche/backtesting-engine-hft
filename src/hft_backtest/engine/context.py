"""Per-event context handed to `Strategy.on_event`.

A fresh context is built each event. Strategies should not retain
references across events — `now` and `book` will be stale on the next
tick, and any captured order id is the strategy's own bookkeeping.

The exposed surface mirrors what TASKS.md M6 specifies: `book`, `now`,
`place`, `cancel`. Anything beyond that (status lookups, fill history)
belongs to the strategy's internal state.
"""

from __future__ import annotations

from hft_backtest.data.events import Side
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders.manager import OrderManager
from hft_backtest.orders.order import Order


class EngineContext:
    __slots__ = ("_book", "_om", "_now")

    def __init__(self, book: OrderBook, order_manager: OrderManager, now: int) -> None:
        self._book = book
        self._om = order_manager
        self._now = now

    @property
    def book(self) -> OrderBook:
        return self._book

    @property
    def now(self) -> int:
        return self._now

    def place(self, side: Side, price: float, size: float) -> Order:
        return self._om.place(side, price, size, self._now)

    def cancel(self, order_id: int) -> Order:
        return self._om.cancel(order_id)
