#!/usr/bin/env python
"""CLI wrapper — equivalent to ``python -m hft_backtest <config.yaml>``.

Usage::

    python scripts/run_backtest.py configs/examples/market_maker.yaml
"""

from hft_backtest.__main__ import main

if __name__ == "__main__":
    main()
