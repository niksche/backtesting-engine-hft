"""Typed backtest configuration — loaded from YAML.

Every config field is validated at load time so the engine code never
deals with untyped dicts or missing keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a config file is invalid or has missing/extra keys."""


@dataclass
class StrategyConfig:
    """Which strategy to run, with its parameters."""

    name: str  # "market_maker" or "noop"
    params: dict[str, float] = field(default_factory=dict)


@dataclass
class BacktestConfig:
    """Top-level backtest configuration."""

    lob_path: Path
    trades_path: Path
    output_dir: Path
    strategy: StrategyConfig
    partial_fills: bool = False

    def validate(self) -> None:
        """Check that referenced data files exist."""
        if not self.lob_path.exists():
            raise ConfigError(f"lob_path does not exist: {self.lob_path}")
        if not self.trades_path.exists():
            raise ConfigError(f"trades_path does not exist: {self.trades_path}")
        if self.strategy.name not in _KNOWN_STRATEGIES:
            raise ConfigError(
                f"unknown strategy '{self.strategy.name}', "
                f"known: {sorted(_KNOWN_STRATEGIES)}"
            )


_KNOWN_STRATEGIES = {"noop", "market_maker"}
_TOP_KEYS = {"lob_path", "trades_path", "output_dir", "strategy", "partial_fills"}
_STRATEGY_KEYS = {"name", "params"}


def load_config(path: str | Path) -> BacktestConfig:
    """Load and validate a YAML config file.

    Raises `ConfigError` on schema violations.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")

    with open(path) as f:
        raw: Any = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError("config must be a YAML mapping")

    unknown = set(raw.keys()) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"unknown top-level keys: {unknown}")

    for required in ("lob_path", "trades_path", "strategy"):
        if required not in raw:
            raise ConfigError(f"missing required key: '{required}'")

    # Resolve paths relative to the config file's directory.
    config_dir = path.resolve().parent

    lob_path = _resolve_path(raw["lob_path"], config_dir)
    trades_path = _resolve_path(raw["trades_path"], config_dir)
    output_dir = _resolve_path(raw.get("output_dir", "reports"), config_dir)

    strategy_raw = raw["strategy"]
    if not isinstance(strategy_raw, dict):
        raise ConfigError("'strategy' must be a mapping")
    unknown_s = set(strategy_raw.keys()) - _STRATEGY_KEYS
    if unknown_s:
        raise ConfigError(f"unknown strategy keys: {unknown_s}")
    if "name" not in strategy_raw:
        raise ConfigError("strategy must have a 'name'")

    strategy = StrategyConfig(
        name=strategy_raw["name"],
        params={str(k): float(v) for k, v in strategy_raw.get("params", {}).items()},
    )

    config = BacktestConfig(
        lob_path=lob_path,
        trades_path=trades_path,
        output_dir=output_dir,
        strategy=strategy,
        partial_fills=bool(raw.get("partial_fills", False)),
    )
    return config


def _resolve_path(p: str, base: Path) -> Path:
    """Resolve a path string relative to `base` unless it's already absolute."""
    pp = Path(p)
    if pp.is_absolute():
        return pp
    return (base / pp).resolve()
