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


# ---------- partial fills (M11 placeholder) ------------------------------


def test_partial_fills_enabled_raises_not_implemented() -> None:
    """Flag is wired through but the behavior lands in M11."""
    me = MatchingEngine(partial_fills_enabled=True)
    o = _placed_buy(100.0)
    with pytest.raises(NotImplementedError, match="M11"):
        me.on_trade(_trade(99.0, Side.SELL), [o])
