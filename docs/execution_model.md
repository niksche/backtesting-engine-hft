# Execution Model

## Overview

The matching engine (`execution/matcher.py`) determines when a resting
limit order fills. It processes two kinds of market events:

1. **Trade prints** — a transaction occurred on the exchange.
2. **Quote updates** — the L2 book changed.

Each event type uses a different crossing rule.

## Crossing Rules

### Trade Prints — Inclusive Crossing

A resting order fills when a trade print satisfies:

- **BUY** at price P fills when `trade.side == SELL` and `trade.price <= P`.
- **SELL** at price P fills when `trade.side == BUY` and `trade.price >= P`.

The aggressor-side check is critical: a buy trade (aggressor buying)
drains asks — it doesn't interact with our resting bid. Only a sell
trade (aggressor selling) can fill our bid.

Inclusive means at-parity fills: if we bid at 100 and a sell prints at
100, we get filled.

### Quote Updates — Strict Crossing

A resting order fills when the book moves through the order's price:

- **BUY** at price P fills when `best_ask < P`.
- **SELL** at price P fills when `best_bid > P`.

Strict (not ≤ / ≥) avoids spurious fills. When we place a buy at 100
and the ask is at 100, we're in queue — not filled. We fill only when
the ask drops *below* our price, implying the market has traded through us.

### Why Two Rules?

Trade prints give us direct evidence that a transaction occurred at a
price that would have crossed our order. Quote updates give us indirect
evidence that the market has moved through our level (the book changed
without a corresponding trade in our data window).

Using inclusive on trades and strict on quotes is a conservative middle
ground:
- We don't miss fills from actual transactions (inclusive on trades).
- We don't over-count fills from quote jitter (strict on quotes).

## Fill Price

All fills execute at the **resting order's limit price**. There is no
price improvement. This is the standard conservative assumption for
backtesting: you get your limit, nothing better.

## Fill Size

With `partial_fills_enabled = False` (default), every fill is full-size.
If a trade of 0.1 crosses our resting order of size 100, the entire 100
fills. This overestimates fill rates but simplifies the core engine.

With `partial_fills_enabled = True` (M11), fill size is
`min(order.remaining_size, trade.amount)`. The order stays active until
fully filled. Quote-triggered fills remain full-size (we have no volume
information from a quote update).

## Order Lifecycle

```
NEW ──▶ FILLED       (full fill)
NEW ──▶ CANCELLED    (strategy cancels)
NEW ──▶ PARTIALLY_FILLED ──▶ FILLED    (partial fills, M11)
```

Orders are placed via `EngineContext.place()` and cancelled via
`EngineContext.cancel()`. The matching engine mutates `Order.status` and
`Order.filled_size` directly on fill.

## Latency Semantics

Orders placed by a strategy in response to event E are not eligible for
matching against event E. They become eligible starting from event E+1.
This models the real-world constraint that you can't trade against
information you haven't finished processing yet.
