"""Integration test: CLI entry point smoke test."""

from __future__ import annotations

from pathlib import Path

from hft_backtest.__main__ import main
from hft_backtest.engine.config import load_config

CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent / "configs"


def test_load_market_maker_config() -> None:
    """Config file parses without error and points to real data."""
    config = load_config(CONFIGS_DIR / "examples" / "market_maker.yaml")
    assert config.strategy.name == "market_maker"
    assert config.lob_path.exists()
    assert config.trades_path.exists()


def test_load_default_config() -> None:
    config = load_config(CONFIGS_DIR / "default.yaml")
    assert config.strategy.name == "noop"
    assert config.lob_path.exists()
    assert config.trades_path.exists()


def test_cli_market_maker(tmp_path: Path) -> None:
    """Smoke test: run the CLI programmatically with a temp output dir."""
    # Write a config that points to sample data but outputs to tmp.
    config_text = f"""
lob_path: {CONFIGS_DIR.parent / "data" / "samples" / "lob_sample.csv"}
trades_path: {CONFIGS_DIR.parent / "data" / "samples" / "trades_sample.csv"}
output_dir: {tmp_path / "cli_report"}
strategy:
  name: market_maker
  params:
    half_spread: 0.0
    size: 100.0
"""
    cfg_file = tmp_path / "test_config.yaml"
    cfg_file.write_text(config_text)

    main([str(cfg_file)])

    assert (tmp_path / "cli_report" / "report.md").exists()
    assert (tmp_path / "cli_report" / "equity_curve.png").exists()
