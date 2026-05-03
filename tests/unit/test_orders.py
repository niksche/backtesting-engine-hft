"""Unit tests for hft_backtest.orders."""

from __future__ import annotations

import pytest

from hft_backtest.data.events import Side
from hft_backtest.orders import (
    Order,
    OrderAlreadyDoneError,
    OrderManager,
    OrderStatus,
    UnknownOrderError,
)


# ---------- Order dataclass ----------------------------------------------


def test_order_defaults_to_new_and_zero_filled() -> None:
    o = Order(id=1, side=Side.BUY, price=100.0, size=5.0, ts=0)
    assert o.status is OrderStatus.NEW
    assert o.filled_size == 0.0


def test_order_is_active_only_while_new() -> None:
    o = Order(id=1, side=Side.BUY, price=100.0, size=5.0, ts=0)
    assert o.is_active is True
    o.status = OrderStatus.CANCELLED
    assert o.is_active is False
    o.status = OrderStatus.FILLED
    assert o.is_active is False


def test_order_remaining_size() -> None:
    o = Order(id=1, side=Side.BUY, price=100.0, size=5.0, ts=0)
    assert o.remaining_size == 5.0
    o.filled_size = 2.0
    assert o.remaining_size == 3.0
    o.filled_size = 5.0
    assert o.remaining_size == 0.0


# ---------- place --------------------------------------------------------


def test_place_creates_order_with_status_new() -> None:
    om = OrderManager()
    o = om.place(Side.BUY, price=100.0, size=5.0, ts=1000)
    assert o.status is OrderStatus.NEW
    assert o.side is Side.BUY
    assert o.price == 100.0
    assert o.size == 5.0
    assert o.ts == 1000
    assert o.filled_size == 0.0


def test_place_assigns_monotonic_unique_ids() -> None:
    om = OrderManager()
    ids = [om.place(Side.BUY, 100.0, 1.0, 0).id for _ in range(5)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_place_ids_continue_after_cancellation() -> None:
    om = OrderManager()
    o1 = om.place(Side.BUY, 100.0, 1.0, 0)
    om.cancel(o1.id)
    o2 = om.place(Side.BUY, 100.0, 1.0, 0)
    assert o2.id > o1.id


def test_place_rejects_zero_size() -> None:
    om = OrderManager()
    with pytest.raises(ValueError, match="size"):
        om.place(Side.BUY, 100.0, 0.0, 0)


def test_place_rejects_negative_size() -> None:
    om = OrderManager()
    with pytest.raises(ValueError, match="size"):
        om.place(Side.BUY, 100.0, -1.0, 0)


def test_place_rejects_zero_price() -> None:
    om = OrderManager()
    with pytest.raises(ValueError, match="price"):
        om.place(Side.BUY, 0.0, 1.0, 0)


def test_place_rejects_negative_price() -> None:
    om = OrderManager()
    with pytest.raises(ValueError, match="price"):
        om.place(Side.BUY, -1.0, 1.0, 0)


# ---------- active() -----------------------------------------------------


def test_active_lists_only_new_orders() -> None:
    om = OrderManager()
    o1 = om.place(Side.BUY, 100.0, 1.0, 0)
    o2 = om.place(Side.SELL, 101.0, 1.0, 0)
    o3 = om.place(Side.BUY, 99.0, 1.0, 0)
    assert {o.id for o in om.active()} == {o1.id, o2.id, o3.id}


def test_active_excludes_cancelled() -> None:
    om = OrderManager()
    o1 = om.place(Side.BUY, 100.0, 1.0, 0)
    o2 = om.place(Side.SELL, 101.0, 1.0, 0)
    om.cancel(o1.id)
    active_ids = {o.id for o in om.active()}
    assert active_ids == {o2.id}


def test_active_excludes_filled() -> None:
    om = OrderManager()
    o1 = om.place(Side.BUY, 100.0, 1.0, 0)
    o2 = om.place(Side.SELL, 101.0, 1.0, 0)
    # Simulate a fill (matcher mutates status directly).
    o1.status = OrderStatus.FILLED
    o1.filled_size = o1.size
    active_ids = {o.id for o in om.active()}
    assert active_ids == {o2.id}


def test_active_iterates_in_placement_order() -> None:
    om = OrderManager()
    placed_ids = [om.place(Side.BUY, 100.0, 1.0, 0).id for _ in range(3)]
    assert [o.id for o in om.active()] == placed_ids


# ---------- cancel -------------------------------------------------------


def test_cancel_marks_status_cancelled_and_returns_order() -> None:
    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 1.0, 0)
    cancelled = om.cancel(o.id)
    assert cancelled is o
    assert o.status is OrderStatus.CANCELLED


def test_cancel_unknown_id_raises() -> None:
    om = OrderManager()
    with pytest.raises(UnknownOrderError):
        om.cancel(42)


def test_cancel_already_cancelled_raises() -> None:
    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 1.0, 0)
    om.cancel(o.id)
    with pytest.raises(OrderAlreadyDoneError):
        om.cancel(o.id)


def test_cancel_filled_raises() -> None:
    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 1.0, 0)
    o.status = OrderStatus.FILLED  # simulated fill
    with pytest.raises(OrderAlreadyDoneError):
        om.cancel(o.id)


# ---------- get ----------------------------------------------------------


def test_get_returns_active_order() -> None:
    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 1.0, 0)
    assert om.get(o.id) is o


def test_get_returns_cancelled_order() -> None:
    om = OrderManager()
    o = om.place(Side.BUY, 100.0, 1.0, 0)
    om.cancel(o.id)
    assert om.get(o.id) is o
    assert om.get(o.id).status is OrderStatus.CANCELLED


def test_get_unknown_raises() -> None:
    om = OrderManager()
    with pytest.raises(UnknownOrderError):
        om.get(99)


# ---------- len ----------------------------------------------------------


def test_len_counts_all_placed_regardless_of_status() -> None:
    om = OrderManager()
    o1 = om.place(Side.BUY, 100.0, 1.0, 0)
    om.place(Side.SELL, 101.0, 1.0, 0)
    om.cancel(o1.id)
    assert len(om) == 2


def test_len_starts_at_zero() -> None:
    assert len(OrderManager()) == 0
