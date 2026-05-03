# HFT Backtesting Engine

A Python backtesting engine for high-frequency trading strategies.
Replays historical L2 order book snapshots and trades, simulates
limit-order placement and fills against a reconstructed book, and
reports PnL, inventory, and turnover.

## Quickstart

### Install

```bash
# Clone and install in a virtual environment
git clone <repo-url>
cd backtesting-engine
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run the Sample

```bash
# Market-maker strategy on the 30-second sample dataset
python -m hft_backtest configs/examples/market_maker.yaml
```

This produces a report directory at `reports/market_maker/` containing:
- `report.md` — summary statistics
- `equity_curve.png`, `inventory.png`, `turnover.png` — charts

### Run Tests

```bash
pytest -v
```

## Project Structure

```
src/hft_backtest/
├── data/           # CSV loaders, event types, EventStream merge
├── orderbook/      # L2 book reconstruction from snapshots
├── orders/         # Order dataclass, status, lifecycle management
├── execution/      # Matching engine — crossing rules, fill emission
├── engine/         # Backtest driver, context, config loader
├── strategies/     # Strategy base class + NaiveMarketMaker
├── metrics/        # PnL, inventory, turnover trackers + recorder
└── reporting/      # Markdown + PNG report generation
```

## Configuration

Backtests are configured via YAML files. Example:

```yaml
lob_path: data/samples/lob_sample.csv
trades_path: data/samples/trades_sample.csv
output_dir: reports/my_run

strategy:
  name: market_maker
  params:
    half_spread: 0.0
    size: 100.0
    repost_threshold: 0.0

partial_fills: false
```

Available strategies: `noop`, `market_maker`.

See `configs/` for example configurations.

## Data

The engine reads two CSV files:

- **`lob.csv`** — L2 order book snapshots (25 levels per side)
- **`trades.csv`** — trade tape

A small 30-second sample is committed in `data/samples/`. Full datasets
are gitignored. See `data/README.md` and `docs/data_format.md` for
schema details.

To carve a new sample from full data:

```bash
python scripts/make_sample.py --seconds 60
```

## Documentation

- [Architecture](docs/architecture.md) — components, event flow
- [Data Format](docs/data_format.md) — CSV schemas, invariants
- [Execution Model](docs/execution_model.md) — crossing rules, fill logic
- [Metrics](docs/metrics.md) — PnL, inventory, turnover formulas
- [Performance Report](docs/performance_report.md) — how to read the output

## Writing a Custom Strategy

Subclass `Strategy` and override the callbacks you need:

```python
from hft_backtest.strategies.base import Strategy
from hft_backtest.strategies.registry import register
from hft_backtest.data.events import LobSnapshot, Trade, Side
from hft_backtest.engine.context import EngineContext
from hft_backtest.execution.fill import Fill

@register("my_strategy")  # makes it available in YAML configs
class MyStrategy(Strategy):

    def on_fill(self, fill: Fill, ctx: EngineContext) -> None:
        """Called when one of our orders fills (before on_event)."""
        print(f"Filled: {fill.side.value} {fill.size} @ {fill.price}")

    def on_snapshot(self, snapshot: LobSnapshot, ctx: EngineContext) -> None:
        """Called on each L2 book update."""
        mid = ctx.book.mid()
        if mid and abs(ctx.position) < 500:
            ctx.place(Side.BUY, mid - 0.001, 10.0)
            ctx.place(Side.SELL, mid + 0.001, 10.0)

    def on_trade(self, trade: Trade, ctx: EngineContext) -> None:
        """Called on each trade print."""
        # Take liquidity to hedge if inventory is too large
        if ctx.position > 200:
            ctx.market_sell(50.0)
        elif ctx.position < -200:
            ctx.market_buy(50.0)
```

### Strategy Callbacks

| Callback | When | Use for |
| -------- | ---- | ------- |
| `on_fill(fill, ctx)` | After each fill on our orders | Inventory tracking, hedging |
| `on_snapshot(snapshot, ctx)` | Each L2 book update | Quoting, signal computation |
| `on_trade(trade, ctx)` | Each trade print | Momentum signals, hedging |
| `on_event(event, ctx)` | Every event (catch-all) | Simple strategies |

### EngineContext API

```python
# Book state
ctx.book                   # OrderBook — mid(), spread(), best_bid(), best_ask(), bids, asks
ctx.now                    # int — current timestamp (µs)

# Limit orders (maker)
ctx.place(side, price, size) -> Order
ctx.cancel(order_id)         -> Order
ctx.cancel_all()             -> list[Order]

# Market orders (taker) — execute immediately
ctx.market_buy(size)         -> Fill | None
ctx.market_sell(size)        -> Fill | None

# Order queries
ctx.get_order(order_id)      -> Order
ctx.active_orders            -> list[Order]

# Event info
ctx.fills                    -> list[Fill]  (fills from this event)

# Position / PnL (requires MetricsRecorder)
ctx.position                 -> float  (net inventory)
ctx.realized_pnl             -> float
ctx.unrealized_pnl           -> float
ctx.total_pnl                -> float
```

### Plugin Registry

Decorate your strategy with `@register("name")` to make it available in
YAML configs:

```yaml
strategy:
  name: my_strategy
  params:
    half_spread: 0.001
    size: 10.0
```

## License

MIT
