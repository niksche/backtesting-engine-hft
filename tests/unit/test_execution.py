"""Unit tests for hft_backtest.execution.matcher."""

from __future__ import annotations

import pytest

from hft_backtest.data.events import Level, LobSnapshot, Side, Trade
from hft_backtest.execution import Fill, MatchingEngine
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders import Order, OrderManager, OrderStatus


def _trade(price: float, side: Side, ts: int = 1000, amount: float = 10.0) -> Trade:
    return Trade(timestamp=ts, side=side, price=price, amount=amount)


def _book_with(bid: float | None, ask: float | None, ts: int = 1000) -> OrderBook:
    bids = (Level(bid, 1.0),) if bid is not None else ()
    asks = (Level(ask, 1.0),) if ask is not None else ()
    book = OrderBook()
    book.apply(LobSnapshot(timestamp=ts, bids=bids, asks=asks))
    return book


def _placed_buy(price: float, size: float = 1.0) -> Order:
    om = OrderManager()
    return om.place(Side.BUY, price, size, ts=0)


def _placed_sell(price: float, size: float = 1.0) -> Order:
    om = OrderManager()
    return om.place(Side.SELL, price, size, ts=0)


# ---------- on_trade: BUY orders -----------------------------------------


def test_buy_fills_when_seller_crosses_below() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_trade(_trade(99.0, Side.SELL), [o])
    assert len(fills) == 1
    assert fills[0].order_id == o.id


def test_buy_fills_when_seller_at_parity() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_trade(_trade(100.0, Side.SELL), [o])
    assert len(fills) == 1


def test_buy_no_fill_when_seller_above() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_trade(_trade(101.0, Side.SELL), [o])
    assert fills == []


def test_buy_no_fill_when_buyer_aggressor_at_same_price() -> None:
    """Aggressor is buying — that drains asks, not our bid."""
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_trade(_trade(100.0, Side.BUY), [o])
    assert fills == []


# ---------- on_trade: SELL orders ----------------------------------------


def test_sell_fills_when_buyer_crosses_above() -> None:
    me = MatchingEngine()
    o = _placed_sell(100.0)
    fills = me.on_trade(_trade(101.0, Side.BUY), [o])
    assert len(fills) == 1


def test_sell_fills_when_buyer_at_parity() -> None:
    me = MatchingEngine()
    o = _placed_sell(100.0)
    fills = me.on_trade(_trade(100.0, Side.BUY), [o])
    assert len(fills) == 1


def test_sell_no_fill_when_buyer_below() -> None:
    me = MatchingEngine()
    o = _placed_sell(100.0)
    fills = me.on_trade(_trade(99.0, Side.BUY), [o])
    assert fills == []


def test_sell_no_fill_when_seller_aggressor_at_same_price() -> None:
    me = MatchingEngine()
    o = _placed_sell(100.0)
    fills = me.on_trade(_trade(100.0, Side.SELL), [o])
    assert fills == []


def test_inactive_order_not_filled_on_trade() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    o.status = OrderStatus.CANCELLED
    fills = me.on_trade(_trade(99.0, Side.SELL), [o])
    assert fills == []


# ---------- on_quote -----------------------------------------------------


def test_buy_fills_when_ask_crosses_strictly() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_quote(_book_with(bid=99.0, ask=99.5), [o])
    assert len(fills) == 1


def test_buy_no_fill_when_ask_at_parity() -> None:
    """Strict crossing on quotes — parity means we're in queue, not filled."""
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_quote(_book_with(bid=99.0, ask=100.0), [o])
    assert fills == []


def test_buy_no_fill_when_ask_above() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_quote(_book_with(bid=99.0, ask=101.0), [o])
    assert fills == []


def test_sell_fills_when_bid_crosses_strictly() -> None:
    me = MatchingEngine()
    o = _placed_sell(100.0)
    fills = me.on_quote(_book_with(bid=100.5, ask=101.0), [o])
    assert len(fills) == 1


def test_sell_no_fill_when_bid_at_parity() -> None:
    me = MatchingEngine()
    o = _placed_sell(100.0)
    fills = me.on_quote(_book_with(bid=100.0, ask=101.0), [o])
    assert fills == []


def test_sell_no_fill_when_bid_below() -> None:
    me = MatchingEngine()
    o = _placed_sell(100.0)
    fills = me.on_quote(_book_with(bid=99.0, ask=101.0), [o])
    assert fills == []


def test_no_fill_when_book_uninitialized() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_quote(OrderBook(), [o])
    assert fills == []


def test_buy_no_fill_when_no_asks_in_book() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_quote(_book_with(bid=99.0, ask=None), [o])
    assert fills == []


def test_sell_no_fill_when_no_bids_in_book() -> None:
    me = MatchingEngine()
    o = _placed_sell(100.0)
    fills = me.on_quote(_book_with(bid=None, ask=101.0), [o])
    assert fills == []


def test_inactive_order_not_filled_on_quote() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    o.status = OrderStatus.CANCELLED
    fills = me.on_quote(_book_with(bid=99.0, ask=99.5), [o])
    assert fills == []


# ---------- multi-order isolation ----------------------------------------


def test_only_crossed_orders_fill_among_many() -> None:
    me = MatchingEngine()
    om = OrderManager()
    far_buy = om.place(Side.BUY, 95.0, 1.0, 0)
    near_buy = om.place(Side.BUY, 100.0, 1.0, 0)
    near_sell = om.place(Side.SELL, 105.0, 1.0, 0)
    far_sell = om.place(Side.SELL, 110.0, 1.0, 0)
    fills = me.on_trade(_trade(99.0, Side.SELL), list(om.active()))
    assert {f.order_id for f in fills} == {near_buy.id}
    assert far_buy.is_active
    assert near_sell.is_active
    assert far_sell.is_active


def test_quote_crossing_buys_and_sells_independently() -> None:
    me = MatchingEngine()
    om = OrderManager()
    buy = om.place(Side.BUY, 100.0, 1.0, 0)
    sell = om.place(Side.SELL, 100.0, 1.0, 0)
    # Book with bid=101 (crosses sell strictly) and ask=99 (crosses buy strictly).
    fills = me.on_quote(_book_with(bid=101.0, ask=99.0), list(om.active()))
    assert {f.order_id for f in fills} == {buy.id, sell.id}


# ---------- fill semantics -----------------------------------------------


def test_fill_sets_order_status_filled_and_size() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0, size=5.0)
    me.on_trade(_trade(99.0, Side.SELL), [o])
    assert o.status is OrderStatus.FILLED
    assert o.filled_size == 5.0
    assert o.remaining_size == 0.0


def test_fill_uses_order_limit_price_not_trade_price() -> None:
    """No price improvement: fill price == order's limit price."""
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_trade(_trade(95.0, Side.SELL), [o])
    assert fills[0].price == 100.0


def test_fill_uses_order_limit_price_on_quote() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    fills = me.on_quote(_book_with(bid=99.0, ask=98.0, ts=2000), [o])
    assert fills[0].price == 100.0
    assert fills[0].timestamp == 2000


def test_fill_carries_correct_size_and_side() -> None:
    me = MatchingEngine()
    o = _placed_sell(100.0, size=7.0)
    fills = me.on_trade(_trade(101.0, Side.BUY), [o])
    assert fills[0] == Fill(
        order_id=o.id, side=Side.SELL, price=100.0, size=7.0, timestamp=1000
    )


def test_repeated_event_does_not_double_fill() -> None:
    me = MatchingEngine()
    o = _placed_buy(100.0)
    trade = _trade(99.0, Side.SELL)
    first = me.on_trade(trade, [o])
    second = me.on_trade(trade, [o])
    assert len(first) == 1
    assert second == []


# ---------- partial fills (M11) ------------------------------------------


def test_partial_fill_basic() -> None:
    """Trade of 3.0 against order of 10.0 → partial fill of 3.0."""
    me = MatchingEngine(partial_fills_enabled=True)
    o = _placed_buy(100.0, size=10.0)
    fills = me.on_trade(_trade(99.0, Side.SELL, amount=3.0), [o])
    assert len(fills) == 1
    assert fills[0].size == 3.0
    assert o.filled_size == 3.0
    assert o.remaining_size == 7.0
    assert o.status is OrderStatus.PARTIALLY_FILLED
    assert o.is_active


def test_partial_fill_completes_order() -> None:
    """Trade large enough to fully fill the order."""
    me = MatchingEngine(partial_fills_enabled=True)
    o = _placed_buy(100.0, size=5.0)
    fills = me.on_trade(_trade(99.0, Side.SELL, amount=10.0), [o])
    assert len(fills) == 1
    assert fills[0].size == 5.0
    assert o.status is OrderStatus.FILLED
    assert not o.is_active


def test_partial_fill_exact_size() -> None:
    """Trade amount exactly matches order size → full fill."""
    me = MatchingEngine(partial_fills_enabled=True)
    o = _placed_buy(100.0, size=5.0)
    fills = me.on_trade(_trade(99.0, Side.SELL, amount=5.0), [o])
    assert fills[0].size == 5.0
    assert o.status is OrderStatus.FILLED


def test_partial_fill_multiple_orders_share_trade_volume() -> None:
    """Trade of 15.0 fills two orders of 10.0 each: first gets 10, second gets 5."""
    me = MatchingEngine(partial_fills_enabled=True)
    om = OrderManager()
    o1 = om.place(Side.BUY, 100.0, 10.0, ts=0)
    o2 = om.place(Side.BUY, 100.0, 10.0, ts=0)
    fills = me.on_trade(
        _trade(99.0, Side.SELL, amount=15.0), list(om.active())
    )
    assert len(fills) == 2
    assert fills[0].size == 10.0
    assert fills[1].size == 5.0
    assert o1.status is OrderStatus.FILLED
    assert o2.status is OrderStatus.PARTIALLY_FILLED
    assert o2.filled_size == 5.0


def test_partial_fill_trade_volume_exhausted_before_all_orders() -> None:
    """Trade of 5.0 only fills the first order; second is untouched."""
    me = MatchingEngine(partial_fills_enabled=True)
    om = OrderManager()
    o1 = om.place(Side.BUY, 100.0, 10.0, ts=0)
    o2 = om.place(Side.BUY, 100.0, 10.0, ts=0)
    fills = me.on_trade(
        _trade(99.0, Side.SELL, amount=5.0), list(om.active())
    )
    assert len(fills) == 1
    assert fills[0].order_id == o1.id
    assert o1.status is OrderStatus.PARTIALLY_FILLED
    assert o2.status is OrderStatus.NEW


def test_partial_fill_accumulates_across_events() -> None:
    """Two partial fills complete the order."""
    me = MatchingEngine(partial_fills_enabled=True)
    o = _placed_buy(100.0, size=10.0)
    me.on_trade(_trade(99.0, Side.SELL, amount=3.0, ts=100), [o])
    assert o.filled_size == 3.0
    assert o.is_active

    me.on_trade(_trade(99.0, Side.SELL, amount=7.0, ts=200), [o])
    assert o.filled_size == 10.0
    assert o.status is OrderStatus.FILLED


def test_partial_fill_sell_side() -> None:
    """Partial fills work symmetrically for sell orders."""
    me = MatchingEngine(partial_fills_enabled=True)
    o = _placed_sell(100.0, size=10.0)
    fills = me.on_trade(_trade(101.0, Side.BUY, amount=4.0), [o])
    assert fills[0].size == 4.0
    assert o.status is OrderStatus.PARTIALLY_FILLED
    assert o.remaining_size == 6.0


def test_partial_fill_quote_triggered_is_full_size() -> None:
    """Quote-triggered fills are always full-size, even in partial mode."""
    me = MatchingEngine(partial_fills_enabled=True)
    o = _placed_buy(100.0, size=10.0)
    fills = me.on_quote(_book_with(bid=99.0, ask=99.5), [o])
    assert len(fills) == 1
    assert fills[0].size == 10.0
    assert o.status is OrderStatus.FILLED


def test_partial_fill_cancel_partially_filled_order() -> None:
    """A partially filled order can still be cancelled."""
    me = MatchingEngine(partial_fills_enabled=True)
    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 10.0, ts=0)
    me.on_trade(_trade(99.0, Side.SELL, amount=3.0), [o])
    assert o.status is OrderStatus.PARTIALLY_FILLED

    cancelled = om.cancel(o.id)
    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.filled_size == 3.0

