"""M0 smoke test — confirms the package imports and pytest is wired up."""

import hft_backtest


def test_package_imports() -> None:
    assert hft_backtest.__version__ == "0.0.1"
