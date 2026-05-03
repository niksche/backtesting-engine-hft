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

Subclass `Strategy` and implement `on_event`:

```python
from hft_backtest.strategies.base import Strategy
from hft_backtest.data.events import MarketEvent, LobSnapshot, Side
from hft_backtest.engine.context import EngineContext

class MyStrategy(Strategy):
    def on_event(self, event: MarketEvent, ctx: EngineContext) -> None:
        if isinstance(event, LobSnapshot):
            mid = ctx.book.mid()
            if mid is not None:
                ctx.place(Side.BUY, mid - 0.01, 10.0)
```

The `EngineContext` provides:
- `ctx.book` — current order book state
- `ctx.now` — event timestamp
- `ctx.place(side, price, size)` — place a resting limit order
- `ctx.cancel(order_id)` — cancel an active order

## License

MIT
