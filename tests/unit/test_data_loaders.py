"""Unit tests for hft_backtest.data — loaders + event stream."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from hft_backtest.data.event_stream import EventStream
from hft_backtest.data.events import Level, LobSnapshot, Side, Trade
from hft_backtest.data.loaders import LobLoader, TradesLoader

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


# ---------- LobLoader ----------------------------------------------------


def test_lob_loader_parses_fixture_file() -> None:
    snapshots = list(LobLoader(FIXTURES / "lob_tiny.csv"))
    assert len(snapshots) == 3
    s0 = snapshots[0]
    assert s0.timestamp == 1000
    assert s0.asks[0] == Level(100.5, 10.0)
    assert s0.bids[0] == Level(100.4, 5.0)
    assert s0.asks[1] == Level(100.6, 20.0)
    assert s0.bids[1] == Level(100.3, 8.0)


def test_lob_loader_auto_detects_level_count() -> None:
    snapshots = list(LobLoader(FIXTURES / "lob_tiny.csv"))
    assert len(snapshots[0].bids) == 2
    assert len(snapshots[0].asks) == 2


def test_lob_loader_accepts_stringio() -> None:
    csv_text = (
        ",local_timestamp,asks[0].price,asks[0].amount,bids[0].price,bids[0].amount\n"
        "0,500,1.0,2.0,0.9,3.0\n"
    )
    snaps = list(LobLoader(io.StringIO(csv_text)))
    assert len(snaps) == 1
    assert snaps[0].timestamp == 500
    assert snaps[0].asks == (Level(1.0, 2.0),)
    assert snaps[0].bids == (Level(0.9, 3.0),)


def test_lob_loader_handles_header_only() -> None:
    csv_text = ",local_timestamp,asks[0].price,asks[0].amount,bids[0].price,bids[0].amount\n"
    assert list(LobLoader(io.StringIO(csv_text))) == []


def test_lob_loader_handles_completely_empty() -> None:
    assert list(LobLoader(io.StringIO(""))) == []


def test_lob_loader_rejects_header_without_asks() -> None:
    csv_text = ",local_timestamp,foo,bar\n"
    with pytest.raises(ValueError, match="asks"):
        list(LobLoader(io.StringIO(csv_text)))


def test_lob_loader_accepts_string_path() -> None:
    snaps = list(LobLoader(str(FIXTURES / "lob_tiny.csv")))
    assert len(snaps) == 3


def test_lob_loader_timestamps_non_decreasing_in_fixture() -> None:
    ts = [s.timestamp for s in LobLoader(FIXTURES / "lob_tiny.csv")]
    assert ts == sorted(ts)


# ---------- TradesLoader -------------------------------------------------


def test_trades_loader_parses_fixture_file() -> None:
    trades = list(TradesLoader(FIXTURES / "trades_tiny.csv"))
    assert len(trades) == 3
    assert trades[0] == Trade(timestamp=1500, side=Side.BUY, price=100.5, amount=3.0)
    assert trades[1].side == Side.SELL
    assert trades[2] == Trade(timestamp=3500, side=Side.BUY, price=100.6, amount=1.0)


def test_trades_loader_handles_header_only() -> None:
    csv_text = ",local_timestamp,side,price,amount\n"
    assert list(TradesLoader(io.StringIO(csv_text))) == []


def test_trades_loader_handles_completely_empty() -> None:
    assert list(TradesLoader(io.StringIO(""))) == []


def test_trades_loader_rejects_invalid_side() -> None:
    csv_text = ",local_timestamp,side,price,amount\n0,100,foo,1.0,1.0\n"
    with pytest.raises(ValueError):
        list(TradesLoader(io.StringIO(csv_text)))


# ---------- EventStream --------------------------------------------------


def _trade(ts: int) -> Trade:
    return Trade(timestamp=ts, side=Side.BUY, price=1.0, amount=1.0)


def _snap(ts: int) -> LobSnapshot:
    return LobSnapshot(timestamp=ts, bids=(), asks=())


def test_event_stream_merges_in_timestamp_order() -> None:
    lob = [_snap(100), _snap(300)]
    trades = [_trade(50), _trade(200), _trade(400)]
    out = list(EventStream(lob, trades))
    assert [e.timestamp for e in out] == [50, 100, 200, 300, 400]


def test_event_stream_non_decreasing_timestamps() -> None:
    lob = [_snap(t) for t in (10, 20, 30)]
    trades = [_trade(t) for t in (5, 25, 35)]
    out = list(EventStream(lob, trades))
    timestamps = [e.timestamp for e in out]
    assert timestamps == sorted(timestamps)


def test_event_stream_lob_first_on_tie() -> None:
    out = list(EventStream([_snap(100)], [_trade(100)]))
    assert isinstance(out[0], LobSnapshot)
    assert isinstance(out[1], Trade)


def test_event_stream_handles_empty_lob() -> None:
    out = list(EventStream([], [_trade(10)]))
    assert len(out) == 1
    assert isinstance(out[0], Trade)


def test_event_stream_handles_empty_trades() -> None:
    out = list(EventStream([_snap(10)], []))
    assert len(out) == 1
    assert isinstance(out[0], LobSnapshot)


def test_event_stream_handles_both_empty() -> None:
    assert list(EventStream([], [])) == []


def test_event_stream_works_with_loaders() -> None:
    """Plug real loaders into the stream — fixture-level sanity check."""
    lob = LobLoader(FIXTURES / "lob_tiny.csv")
    trades = TradesLoader(FIXTURES / "trades_tiny.csv")
    out = list(EventStream(lob, trades))
    assert [e.timestamp for e in out] == [1000, 1500, 2000, 2500, 3000, 3500]
