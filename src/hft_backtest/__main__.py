"""CLI entry point: ``python -m hft_backtest <config.yaml>``

Loads a YAML config, builds all components, runs the backtest, and
writes the performance report.
"""

from __future__ import annotations

import argparse
import sys

from hft_backtest.data.event_stream import EventStream
from hft_backtest.data.loaders import LobLoader, TradesLoader
from hft_backtest.engine.backtest import Backtest
from hft_backtest.engine.config import BacktestConfig, ConfigError, load_config
from hft_backtest.execution.matcher import MatchingEngine
from hft_backtest.metrics.recorder import MetricsRecorder
from hft_backtest.orderbook.book import OrderBook
from hft_backtest.orders.manager import OrderManager
from hft_backtest.reporting.report import generate_report
from hft_backtest.strategies.base import Strategy
from hft_backtest.strategies.market_maker import NaiveMarketMaker


def _build_strategy(config: BacktestConfig) -> Strategy:
    """Instantiate the strategy from config."""
    if config.strategy.name == "noop":
        return Strategy()
    if config.strategy.name == "market_maker":
        params = config.strategy.params
        return NaiveMarketMaker(
            half_spread=params.get("half_spread", 0.0),
            size=params.get("size", 1.0),
            repost_threshold=params.get("repost_threshold", 0.0),
        )
    raise ConfigError(f"unknown strategy: {config.strategy.name}")


def run_backtest(config: BacktestConfig) -> None:
    """Execute a full backtest from a validated config."""
    config.validate()

    print(f"Loading data: {config.lob_path}, {config.trades_path}")
    events = EventStream(LobLoader(config.lob_path), TradesLoader(config.trades_path))

    strategy = _build_strategy(config)
    recorder = MetricsRecorder()

    print(f"Running backtest with strategy: {config.strategy.name}")
    bt = Backtest(
        events=events,
        book=OrderBook(),
        order_manager=OrderManager(),
        matcher=MatchingEngine(partial_fills_enabled=config.partial_fills),
        strategy=strategy,
        recorder=recorder,
    )
    fills = bt.run()

    print(f"Fills: {len(fills)}")
    print(f"Generating report → {config.output_dir}")
    generate_report(recorder.snapshots, config.output_dir)
    print("Done.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="hft-backtest",
        description="Run an HFT backtest from a YAML config file.",
    )
    parser.add_argument("config", help="Path to the YAML config file.")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        run_backtest(config)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
