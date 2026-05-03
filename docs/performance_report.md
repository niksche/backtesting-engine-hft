# Performance Report

## What Gets Generated

Running a backtest produces an output directory containing:

```
reports/<name>/
├── report.md          # Summary statistics table
├── equity_curve.png   # Total PnL over time
├── inventory.png      # Signed inventory over time
└── turnover.png       # Cumulative notional traded
```

## Reading the Report

### Summary Statistics Table

| Metric | What It Tells You |
| ------ | ----------------- |
| **Realized PnL** | Profit/loss from closed trades. |
| **Unrealized PnL** | Paper profit/loss on open inventory at end of run. |
| **Total PnL** | Realized + unrealized. The bottom line. |
| **Max Drawdown** | Largest peak-to-trough drop in total PnL. A risk measure — how much you'd have lost from the worst entry point. |
| **Sharpe Ratio** | Mean return per unit risk, computed per-snapshot. Higher is better; negative means the strategy lost money on average. |
| **Fill Count** | Total executions. More fills ≠ better, but zero fills means the strategy never traded. |
| **Avg Abs Inventory** | Average absolute position held. High values mean the strategy carries significant directional risk. |
| **Peak Abs Inventory** | Maximum position size. Indicates worst-case capital requirement. |
| **Total Turnover** | Cumulative notional traded. Proxy for transaction costs in a real deployment. |

### Equity Curve

The total PnL plotted over time. Look for:
- **Trend**: upward = profitable strategy, downward = losing.
- **Volatility**: smooth curves are better risk-adjusted than jagged ones.
- **Drawdowns**: deep dips indicate periods of loss.

### Inventory Plot

Signed position over time. Look for:
- **Mean-reversion**: good market-makers oscillate around zero.
- **Drift**: sustained long/short exposure indicates directional bias.
- **Peak size**: large positions amplify both gains and losses.

### Turnover Plot

Cumulative notional traded. A steeper slope means more trading activity.
In live deployment, turnover correlates with transaction costs (fees,
spread crossing).

## Generating a Report

```bash
python -m hft_backtest configs/examples/market_maker.yaml
```

The output directory is set in the config file (`output_dir`). Default
configs write to `reports/`.
