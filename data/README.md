# Data

This directory holds market-data inputs to the backtester.

## Files

| File              | Committed | Purpose                                       |
| ----------------- | --------- | --------------------------------------------- |
| `lob.csv`         | No        | Full L2 snapshot stream (~1 GB).              |
| `trades.csv`      | No        | Full trade tape (~1 GB).                      |
| `samples/*.csv`   | Yes       | Small carve-outs for tests + demos (< 5 MB). |

`lob.csv` and `trades.csv` are listed in `.gitignore`. The committed `samples/`
carve-outs are produced by `scripts/make_sample.py` (see M1 in `TASKS.md`).

## `lob.csv` — L2 order book snapshots

One row per snapshot. 25 levels per side.

```
,local_timestamp,asks[0].price,asks[0].amount,bids[0].price,bids[0].amount,
                 asks[1].price,asks[1].amount,bids[1].price,bids[1].amount,
                 ...,
                 asks[24].price,asks[24].amount,bids[24].price,bids[24].amount
```

| Column            | Type   | Notes                                              |
| ----------------- | ------ | -------------------------------------------------- |
| (unnamed index)   | int    | Row index from the source dump. Ignore on load.    |
| `local_timestamp` | int64  | Microseconds since Unix epoch.                     |
| `asks[i].price`   | float  | Ask price at level `i` (0 = best). Strictly increasing in `i`. |
| `asks[i].amount`  | float  | Ask size at level `i`. Non-negative.               |
| `bids[i].price`   | float  | Bid price at level `i` (0 = best). Strictly decreasing in `i`. |
| `bids[i].amount`  | float  | Bid size at level `i`. Non-negative.               |

Invariants the loader (M1) and book (M2) rely on:
- `bids[0].price < asks[0].price` on every row (no crossed book in source).
- All sizes ≥ 0.
- Timestamps are non-decreasing across rows.

## `trades.csv` — trade tape

One row per trade print.

```
,local_timestamp,side,price,amount
```

| Column            | Type   | Notes                                              |
| ----------------- | ------ | -------------------------------------------------- |
| (unnamed index)   | int    | Row index from the source dump. Ignore on load.    |
| `local_timestamp` | int64  | Microseconds since Unix epoch.                     |
| `side`            | str    | `"buy"` or `"sell"` — aggressor side.              |
| `price`           | float  | Trade price.                                       |
| `amount`          | float  | Trade size. Non-negative.                          |

## Provenance

The full files were captured externally (timestamps suggest August 2024).
Treat them as read-only inputs; do not edit in place. The instrument is a
small-tick crypto pair (prices on the order of 1e-2).
