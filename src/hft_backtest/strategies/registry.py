"""Strategy plugin registry.

Strategies register themselves with the ``@register`` decorator::

    @register("my_strategy")
    class MyStrategy(Strategy):
        def __init__(self, param1: float = 1.0):
            ...

Then they can be instantiated from a YAML config by name::

    strategy = build_strategy("my_strategy", {"param1": 2.0})
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hft_backtest.strategies.base import Strategy

_REGISTRY: dict[str, type[Strategy]] = {}


def register(name: str):  # type: ignore[type-arg]
    """Class decorator: register a strategy under ``name``."""

    def decorator(cls: type[Strategy]) -> type[Strategy]:
        if name in _REGISTRY:
            raise ValueError(
                f"strategy name '{name}' is already registered "
                f"by {_REGISTRY[name].__name__}"
            )
        _REGISTRY[name] = cls
        return cls

    return decorator


def build_strategy(name: str, params: dict[str, float]) -> Strategy:
    """Instantiate a registered strategy by name with keyword params."""
    if name not in _REGISTRY:
        available = sorted(_REGISTRY.keys())
        raise KeyError(
            f"unknown strategy '{name}', registered: {available}"
        )
    cls = _REGISTRY[name]
    return cls(**params)  # type: ignore[arg-type]


def registered_names() -> list[str]:
    """Return sorted list of all registered strategy names."""
    return sorted(_REGISTRY.keys())
