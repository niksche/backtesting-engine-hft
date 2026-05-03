# Data Format

## Input Files

The backtester reads two CSV files:

### `lob.csv` — L2 Order Book Snapshots

One row per snapshot. Each row contains 25 price levels per side
(bid + ask), for a total of 101 columns.

**Schema:**

```
,local_timestamp,asks[0].price,asks[0].amount,bids[0].price,bids[0].amount,...,asks[24].price,asks[24].amount,bids[24].price,bids[24].amount
```

| Column | Type | Description |
| ------ | ---- | ----------- |
| (index) | int | Row index from the source dump. Ignored on load. |
| `local_timestamp` | int64 | Microseconds since Unix epoch. |
| `asks[i].price` | float | Ask price at level `i` (0 = best). Strictly increasing in `i`. |
| `asks[i].amount` | float | Ask size at level `i`. Non-negative. |
| `bids[i].price` | float | Bid price at level `i` (0 = best). Strictly decreasing in `i`. |
| `bids[i].amount` | float | Bid size at level `i`. Non-negative. |

**Invariants:**
- `bids[0].price < asks[0].price` (no crossed book in source data).
- All sizes ≥ 0.
- Timestamps are non-decreasing across rows.

The loader auto-detects the number of levels from the header — files with
fewer than 25 levels work fine.

### `trades.csv` — Trade Tape

One row per trade print.

**Schema:**

```
,local_timestamp,side,price,amount
```

| Column | Type | Description |
| ------ | ---- | ----------- |
| (index) | int | Row index from the source dump. Ignored on load. |
| `local_timestamp` | int64 | Microseconds since Unix epoch. |
| `side` | str | `"buy"` or `"sell"` — the aggressor side. |
| `price` | float | Trade price. |
| `amount` | float | Trade size. Non-negative. |

## Sample Data

A 30-second carve-out lives in `data/samples/`:

- `lob_sample.csv` (~53 KB)
- `trades_sample.csv` (~53 KB)

These are produced by `scripts/make_sample.py` from the full datasets and
are committed to the repository for tests and demos.

## Provenance

The full files were captured externally. Timestamps place the data in
August 2024. The instrument is a small-tick crypto pair (prices on the
order of 1e-2). Treat the full files as read-only; they are gitignored.

## Edge Cases

- **Empty files**: both loaders handle header-only and completely empty
  files gracefully (zero events yielded).
- **Timestamps**: the `EventStream` merge uses `heapq.merge` by
  timestamp. On tied timestamps, LOB snapshots are emitted before trades.
- **Level count mismatch**: the loader detects levels from the header, not
  from a hardcoded constant. Files with 1–25 levels all work.
