# Metrics

## PnL (Profit and Loss)

PnL is computed using the **average-cost** method.

### Realized PnL

Accumulated each time a fill reduces (or flips) the position:

- **Long position closed by a sell fill**:
  `realized += closed_qty × (fill_price − avg_entry_price)`
- **Short position closed by a buy fill**:
  `realized += closed_qty × (avg_entry_price − fill_price)`

When a fill adds to an existing position (same direction), the average
entry price is blended:

```
avg_entry = (old_avg × old_qty + fill_price × fill_qty) / new_qty
```

When a fill flips the position through zero, the old position is fully
closed at its average entry price, and the remainder starts a new
position with cost basis at the fill price.

### Unrealized PnL

Mark-to-market against the current mid price:

- **Long**: `unrealized = position × (mid − avg_entry_price)`
- **Short**: `unrealized = |position| × (avg_entry_price − mid)`
- **Flat**: `unrealized = 0`

### Total PnL

```
total_pnl = realized_pnl + unrealized_pnl
```

## Inventory

Signed net position:

```
inventory = Σ (fill_size if BUY else −fill_size)
```

Positive = long, negative = short. Peak statistics track the maximum
long and short positions observed during the run.

## Turnover

Cumulative notional value traded:

```
turnover = Σ (fill_price × fill_size)
```

Both buys and sells contribute. This measures total market exposure
through the backtest.

## Summary Statistics

The report includes:

| Stat | Formula |
| ---- | ------- |
| **Max Drawdown** | Peak-to-trough of the total PnL time series. |
| **Sharpe Ratio** | `mean(Δ_pnl) / std(Δ_pnl)` across consecutive snapshots. Not annualized — it's a per-snapshot ratio. |
| **Avg Abs Inventory** | `mean(|inventory|)` across all snapshots. |
| **Peak Abs Inventory** | `max(|inventory|)` across all snapshots. |
| **Fill Count** | Total number of fills. |

## Snapshot Frequency

Metric snapshots are recorded:
- After **every fill** (captures all inflection points).
- At **end of run** (final mark-to-market).

This avoids excessive memory usage on million-event datasets while
ensuring no fill-driven metric change is missed.
