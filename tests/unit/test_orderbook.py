"""Unit tests for hft_backtest.orderbook.book."""

from __future__ import annotations

from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given

from hft_backtest.data.events import Level, LobSnapshot
from hft_backtest.data.loaders import LobLoader
from hft_backtest.orderbook.book import OrderBook

SAMPLE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "samples" / "lob_sample.csv"
)


def _snap(
    ts: int,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
) -> LobSnapshot:
    return LobSnapshot(
        timestamp=ts,
        bids=tuple(Level(p, a) for p, a in bids),
        asks=tuple(Level(p, a) for p, a in asks),
    )


# ---------- empty / initial state ----------------------------------------


def test_empty_book_has_no_top_of_book() -> None:
    b = OrderBook()
    assert b.best_bid() is None
    assert b.best_ask() is None
    assert b.timestamp is None
    assert b.bids == ()
    assert b.asks == ()


def test_empty_book_mid_and_spread_are_none() -> None:
    b = OrderBook()
    assert b.mid() is None
    assert b.spread() is None


# ---------- apply --------------------------------------------------------


def test_apply_sets_top_of_book_and_timestamp() -> None:
    book = OrderBook()
    book.apply(
        _snap(1000, bids=[(99.0, 5.0), (98.0, 3.0)], asks=[(100.0, 4.0), (101.0, 2.0)])
    )
    assert book.best_bid() == Level(99.0, 5.0)
    assert book.best_ask() == Level(100.0, 4.0)
    assert book.timestamp == 1000


def test_apply_replaces_state() -> None:
    book = OrderBook()
    book.apply(_snap(1000, bids=[(99.0, 5.0)], asks=[(100.0, 4.0)]))
    book.apply(_snap(2000, bids=[(95.0, 1.0)], asks=[(96.0, 2.0)]))
    assert book.best_bid() == Level(95.0, 1.0)
    assert book.best_ask() == Level(96.0, 2.0)
    assert book.timestamp == 2000
    assert len(book.bids) == 1
    assert len(book.asks) == 1


def test_mid_and_spread() -> None:
    book = OrderBook()
    book.apply(_snap(0, bids=[(99.0, 1.0)], asks=[(101.0, 1.0)]))
    assert book.mid() == 100.0
    assert book.spread() == 2.0


def test_mid_and_spread_none_when_no_bids() -> None:
    book = OrderBook()
    book.apply(_snap(0, bids=[], asks=[(101.0, 1.0)]))
    assert book.mid() is None
    assert book.spread() is None


def test_mid_and_spread_none_when_no_asks() -> None:
    book = OrderBook()
    book.apply(_snap(0, bids=[(99.0, 1.0)], asks=[]))
    assert book.mid() is None
    assert book.spread() is None


def test_iteration_order() -> None:
    book = OrderBook()
    book.apply(
        _snap(
            0,
            bids=[(99.0, 1.0), (98.0, 2.0), (97.0, 3.0)],
            asks=[(100.0, 1.0), (101.0, 2.0), (102.0, 3.0)],
        )
    )
    assert [level.price for level in book.bids] == [99.0, 98.0, 97.0]
    assert [level.price for level in book.asks] == [100.0, 101.0, 102.0]


# ---------- real sample --------------------------------------------------


def test_book_first_real_snapshot_uncrossed() -> None:
    snap = next(iter(LobLoader(SAMPLE)))
    book = OrderBook()
    book.apply(snap)
    bb = book.best_bid()
    ba = book.best_ask()
    assert bb is not None and ba is not None
    assert bb.price < ba.price


def test_book_invariants_hold_for_full_sample_replay() -> None:
    book = OrderBook()
    n = 0
    for snap in LobLoader(SAMPLE):
        book.apply(snap)
        bids = book.bids
        asks = book.asks
        for i in range(1, len(bids)):
            assert bids[i].price < bids[i - 1].price
        for i in range(1, len(asks)):
            assert asks[i].price > asks[i - 1].price
        if bids and asks:
            assert bids[0].price < asks[0].price
        for level in bids:
            assert level.amount >= 0
        for level in asks:
            assert level.amount >= 0
        n += 1
    assert n > 0  # sentinel: sample wasn't empty


# ---------- Hypothesis property tests ------------------------------------


@st.composite
def well_formed_snapshot(draw: st.DrawFn) -> LobSnapshot:
    """Generate a snapshot that satisfies the source-data invariants:
    strictly descending bids, strictly ascending asks, no cross, sizes >= 0.
    """
    n_bids = draw(st.integers(min_value=0, max_value=8))
    n_asks = draw(st.integers(min_value=0, max_value=8))
    ts = draw(st.integers(min_value=0, max_value=10**12))
    mid = draw(
        st.floats(
            min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False
        )
    )

    asks: list[Level] = []
    p_a = mid
    for _ in range(n_asks):
        delta = draw(
            st.floats(
                min_value=0.001,
                max_value=10.0,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        p_a = p_a + delta
        amt = draw(
            st.floats(
                min_value=0.0,
                max_value=1e6,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        asks.append(Level(p_a, amt))

    bids: list[Level] = []
    p_b = mid
    for _ in range(n_bids):
        delta = draw(
            st.floats(
                min_value=0.001,
                max_value=10.0,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        p_b = p_b - delta
        amt = draw(
            st.floats(
                min_value=0.0,
                max_value=1e6,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        bids.append(Level(p_b, amt))

    return LobSnapshot(timestamp=ts, bids=tuple(bids), asks=tuple(asks))


@given(snap=well_formed_snapshot())
def test_property_apply_preserves_strict_ordering(snap: LobSnapshot) -> None:
    book = OrderBook()
    book.apply(snap)
    for i in range(1, len(book.bids)):
        assert book.bids[i].price < book.bids[i - 1].price
    for i in range(1, len(book.asks)):
        assert book.asks[i].price > book.asks[i - 1].price


@given(snap=well_formed_snapshot())
def test_property_apply_does_not_cross(snap: LobSnapshot) -> None:
    book = OrderBook()
    book.apply(snap)
    if book.bids and book.asks:
        assert book.bids[0].price < book.asks[0].price


@given(snap=well_formed_snapshot())
def test_property_apply_keeps_sizes_nonneg(snap: LobSnapshot) -> None:
    book = OrderBook()
    book.apply(snap)
    for level in book.bids:
        assert level.amount >= 0
    for level in book.asks:
        assert level.amount >= 0


@given(snaps=st.lists(well_formed_snapshot(), min_size=1, max_size=10))
def test_property_apply_replaces_wholesale(snaps: list[LobSnapshot]) -> None:
    book = OrderBook()
    for s in snaps:
        book.apply(s)
    last = snaps[-1]
    assert book.bids == last.bids
    assert book.asks == last.asks
    assert book.timestamp == last.timestamp


@given(snap=well_formed_snapshot())
def test_property_top_of_book_consistent_with_levels(snap: LobSnapshot) -> None:
    book = OrderBook()
    book.apply(snap)
    if book.bids:
        assert book.best_bid() == book.bids[0]
    else:
        assert book.best_bid() is None
    if book.asks:
        assert book.best_ask() == book.asks[0]
    else:
        assert book.best_ask() is None
