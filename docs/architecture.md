# Architecture

## Overview

The HFT backtesting engine replays historical L2 order book snapshots and
trade prints, simulates limit-order placement and fills against the
reconstructed book, and reports PnL, inventory, and turnover.

## Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Backtest Engine                            │
│                                                                      │
│  ┌──────────────┐    ┌──────────┐    ┌────────────────┐              │
│  │  EventStream  │───▶│ OrderBook │    │ OrderManager   │              │
│  │  (data/)      │    │ (orderbook/)│  │ (orders/)      │              │
│  └──────────────┘    └─────┬────┘    └───────┬────────┘              │
│         │                  │                 │                        │
│         ▼                  ▼                 ▼                        │
│  ┌──────────────────────────────────────────────────┐                │
│  │              MatchingEngine (execution/)          │                │
│  │  on_trade(trade, resting) → fills                 │                │
│  │  on_quote(book, resting)  → fills                 │                │
│  └───────────────────────┬──────────────────────────┘                │
│                          │ fills                                      │
│                          ▼                                            │
│  ┌──────────────────┐  ┌────────────────┐  ┌──────────────────┐      │
│  │  Strategy         │  │ MetricsRecorder│  │  ReportGenerator │      │
│  │  (strategies/)    │  │ (metrics/)     │──▶│  (reporting/)    │      │
│  └──────────────────┘  └────────────────┘  └──────────────────┘      │
└──────────────────────────────────────────────────────────────────────┘
```

## Event Loop

Each iteration of the main loop processes one `MarketEvent`:

1. **Ingest event** from the merged `EventStream` (LOB snapshots + trades,
   sorted by `local_timestamp`).
2. **Update state**: if `LobSnapshot`, apply to `OrderBook`.
3. **Match**: run `MatchingEngine` against all active resting orders.
   - `LobSnapshot` → `on_quote` (strict crossing).
   - `Trade` → `on_trade` (inclusive crossing with aggressor check).
4. **Record**: feed fills to `MetricsRecorder` (PnL, inventory, turnover).
5. **Strategy callback**: `strategy.on_event(event, ctx)` — the strategy
   can place or cancel orders via `EngineContext`.

Orders placed by the strategy in response to event E are eligible for
matching starting from event E+1 (correct latency semantics).

## Data Flow

```
lob.csv ──▶ LobLoader ──┐
                         ├──▶ EventStream ──▶ Backtest.run()
trades.csv ▶ TradesLoader┘                       │
                                                 ▼
                                          MetricsRecorder
                                                 │
                                                 ▼
                                         generate_report()
                                                 │
                                                 ▼
                                     report.md + PNG plots
```

## Module Map

| Module | Responsibility |
| ------ | -------------- |
| `data/` | CSV loaders, event types, timestamp-ordered merge |
| `orderbook/` | L2 book reconstruction from snapshot rows |
| `orders/` | `Order` dataclass, `OrderStatus`, `OrderManager` lifecycle |
| `execution/` | `MatchingEngine` — crossing detection, fill emission |
| `engine/` | `Backtest` driver, `EngineContext`, `BacktestConfig` |
| `strategies/` | `Strategy` base class, `NaiveMarketMaker` |
| `metrics/` | PnL, inventory, turnover trackers + `MetricsRecorder` |
| `reporting/` | Markdown + PNG report generation |

## Performance Notes

The engine is pure Python. On the ~50 KB sample data, a full backtest
(with market-maker + metrics + report) completes in under 1 second.

On the full ~1 GB dataset, the main bottleneck is CSV parsing. If
profiling reveals hotspots, candidates for C++ extension are:

- `EventStream` merge (currently `heapq.merge`)
- `MatchingEngine._trade_crosses` / `_quote_crosses` inner loop
- CSV row parsing (replace `csv.reader` with a Polars scan)

No premature optimization has been applied. The `partial_fills_enabled`
flag adds minimal overhead when disabled (one boolean check per fill).
