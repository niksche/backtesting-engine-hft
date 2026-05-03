"""Per-event context handed to Strategy callbacks.

A fresh context is built each event by the engine. It carries:

- **Book state**: current L2 order book.
- **Order management**: place limit orders (maker), market orders (taker),
  cancel orders, query active orders.
- **Fill info**: fills that occurred on this event, before the strategy
  callback fires.
- **Position / PnL**: current inventory, realized and unrealized PnL
  (read from the MetricsRecorder if attached).

Market orders (`market_buy`, `market_sell`) execute immediately against
the current book at the best available price. They are collected by the
engine after the strategy callback and recorded in the fill log and
metrics like any other fill.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hft_backtest.data.events import Side
from hft_backtest.execution.fill import Fill
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders.manager import OrderManager
from hft_backtest.orders.order import Order
from hft_backtest.orders.status import OrderStatus

if TYPE_CHECKING:
    from hft_backtest.metrics.recorder import MetricsRecorder


class EngineContext:
    __slots__ = (
        "_book",
        "_om",
        "_now",
        "_fills",
        "_recorder",
        "_market_fills",
        "_next_market_id",
    )

    def __init__(
        self,
        book: OrderBook,
        order_manager: OrderManager,
        now: int,
        fills: list[Fill] | None = None,
        recorder: MetricsRecorder | None = None,
    ) -> None:
        self._book = book
        self._om = order_manager
        self._now = now
        self._fills: list[Fill] = fills if fills is not None else []
        self._recorder = recorder
        self._market_fills: list[Fill] = []
        self._next_market_id: int = -1  # negative IDs for market orders

    # --- Book state ---------------------------------------------------------

    @property
    def book(self) -> OrderBook:
        return self._book

    @property
    def now(self) -> int:
        return self._now

    # --- Fills from this event ----------------------------------------------

    @property
    def fills(self) -> list[Fill]:
        """Fills that occurred on this event (before strategy callback)."""
        return self._fills

    # --- Limit orders (maker) -----------------------------------------------

    def place(self, side: Side, price: float, size: float) -> Order:
        """Place a resting limit order. Returns the Order."""
        return self._om.place(side, price, size, self._now)

    def cancel(self, order_id: int) -> Order:
        """Cancel an active order. Returns the cancelled Order."""
        return self._om.cancel(order_id)

    def cancel_all(self) -> list[Order]:
        """Cancel all active orders. Returns list of cancelled Orders."""
        cancelled: list[Order] = []
        for order in list(self.active_orders):
            try:
                self._om.cancel(order.id)
                cancelled.append(order)
            except Exception:
                pass
        return cancelled

    # --- Order queries ------------------------------------------------------

    def get_order(self, order_id: int) -> Order:
        """Look up any order by ID (active, filled, or cancelled)."""
        return self._om.get(order_id)

    @property
    def active_orders(self) -> list[Order]:
        """All currently active (resting) orders."""
        return list(self._om.active())

    # --- Market orders (taker) ----------------------------------------------

    def market_buy(self, size: float) -> Fill | None:
        """Execute an immediate buy at the current best ask.

        Returns the Fill, or None if no ask liquidity.
        """
        ba = self._book.best_ask()
        if ba is None:
            return None
        return self._execute_market_order(Side.BUY, ba.price, size)

    def market_sell(self, size: float) -> Fill | None:
        """Execute an immediate sell at the current best bid.

        Returns the Fill, or None if no bid liquidity.
        """
        bb = self._book.best_bid()
        if bb is None:
            return None
        return self._execute_market_order(Side.SELL, bb.price, size)

    def _execute_market_order(
        self, side: Side, price: float, size: float
    ) -> Fill:
        """Create and immediately fill a market order."""
        # Use a synthetic order to track in the order manager.
        order = self._om.place(side, price, size, self._now)
        order.filled_size = size
        order.status = OrderStatus.FILLED
        fill = Fill(
            order_id=order.id,
            side=side,
            price=price,
            size=size,
            timestamp=self._now,
        )
        self._market_fills.append(fill)
        return fill

    @property
    def market_fills(self) -> list[Fill]:
        """Market-order fills accumulated during this callback (engine use)."""
        return self._market_fills

    # --- Position / PnL (from MetricsRecorder) ------------------------------

    @property
    def position(self) -> float:
        """Current net inventory (positive = long, negative = short)."""
        if self._recorder is not None:
            return self._recorder.pnl.position
        return 0.0

    @property
    def realized_pnl(self) -> float:
        """Cumulative realized PnL."""
        if self._recorder is not None:
            return self._recorder.pnl.realized_pnl
        return 0.0

    @property
    def unrealized_pnl(self) -> float:
        """Current unrealized PnL (mark-to-market)."""
        if self._recorder is not None:
            return self._recorder.pnl.unrealized_pnl
        return 0.0

    @property
    def total_pnl(self) -> float:
        """Realized + unrealized PnL."""
        if self._recorder is not None:
            return self._recorder.pnl.total_pnl
        return 0.0
