# Architecture

## Overview

The High-Performance Electronic Exchange Simulator is structured around **Clean Architecture** principles.
All cross-cutting concerns flow inward: outer layers (dashboard, reporting) depend on inner layers
(core, matching), never the reverse.

```
┌────────────────────────────────────────────────────────────────┐
│                    Presentation Layer                          │
│            Dashboard (Plotly Dash)  |  Reports (HTML/CSV)     │
├────────────────────────────────────────────────────────────────┤
│                    Application Layer                           │
│         Exchange Facade  |  Replay Engine  |  Analytics       │
├────────────────────────────────────────────────────────────────┤
│                      Domain Layer                              │
│     Matching Engine  |  Order Book  |  Execution History      │
├────────────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                         │
│        Order Models  |  Enums  |  Validation  |  Interfaces   │
└────────────────────────────────────────────────────────────────┘
```

---

## Component Diagram

```
                    ┌─────────────────────────────────────┐
                    │          Exchange (Facade)           │
                    │  - submit_order()                   │
                    │  - cancel_order()                   │
                    │  - modify_order()                   │
                    │  - get_market_data()                │
                    └──────────┬──────────────────────────┘
                               │
         ┌─────────────────────┼──────────────────────┐
         ▼                     ▼                       ▼
┌────────────────┐   ┌──────────────────┐   ┌─────────────────┐
│  OrderValidator│   │  MatchingEngine  │   │ MarketData      │
│                │   │                  │   │ Publisher       │
│  - validate()  │   │  - submit()      │   │ - publish()     │
└────────────────┘   │  - cancel()      │   │ - get_latest()  │
                     │  - modify()      │   └─────────────────┘
                     └────────┬─────────┘
                              │
                     ┌────────▼────────────┐
                     │    OrderBook        │
                     │                     │
                     │  Bids: SortedDict   │
                     │  (descending)       │
                     │                     │
                     │  Asks: SortedDict   │
                     │  (ascending)        │
                     │                     │
                     │  PriceLevel:        │
                     │    deque[Order]     │
                     └─────────────────────┘
```

---

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `exchange/interfaces/` | Abstract Base Classes — defines contracts between components |
| `exchange/orders/` | Data models (Order, Trade, ExecutionReport), enums, input validation |
| `exchange/matching/` | Order Book (price levels, FIFO queues), Matching Engine |
| `exchange/core/` | Exchange facade, market data publisher, execution history |
| `exchange/replay/` | CSV-driven historical order replay with configurable speed |
| `exchange/analytics/` | VWAP, spread, depth, imbalance, latency, order flow |
| `exchange/reporting/` | JSON, CSV, HTML report generation via Jinja2 |
| `exchange/dashboard/` | Interactive Plotly Dash web dashboard |
| `tests/` | Unit, integration, stress, and replay correctness tests |
| `benchmarks/` | Throughput (orders/sec) and latency benchmarks |

---

## Data Flow

### Order Submission

```
Client
  │
  ▼ submit_order(order)
Exchange
  │
  ├─► OrderValidator.validate(order)   — raises ValidationError on failure
  │
  ▼ (valid order)
MatchingEngine.submit_order(order)
  │
  ├─► If marketable: match against OrderBook
  │     └─► For each fill: generate Trade, ExecutionReport (FILL)
  │
  ├─► If residual remains (Limit/GTC): add to OrderBook
  │     └─► generate ExecutionReport (RESTING)
  │
  └─► If IOC/FOK with no/partial fill: cancel residual
        └─► generate ExecutionReport (CANCELLED)
  │
  ▼
ExecutionHistory.record(reports)
MarketDataPublisher.publish(book.get_depth())
```

### Replay Flow

```
CSV File
  │
  ▼ ReplayLoader.load(path)
List[Order]
  │
  ▼ ReplayEngine.replay(orders, speed)
Exchange.submit_order(order)  [for each order]
  │
  ▼
Analytics / Reports generated post-replay
```

---

## Order Book Implementation

### Price Level Structure

Each side of the order book is a `SortedDict` (from `sortedcontainers`) mapping price → `PriceLevel`.

- **Bids**: keyed by `-price` (negated) so the highest bid is at index 0 — O(log n)
- **Asks**: keyed by `+price` so the lowest ask is at index 0 — O(log n)

Each `PriceLevel` contains a `collections.deque` of `Order` objects, maintained in arrival order (FIFO).

### Matching Algorithm (Price-Time Priority)

1. Walk ask side (ascending price) against an incoming bid, or bid side (descending) against an incoming ask.
2. At each price level, iterate the FIFO queue.
3. For each resting order:
   - Generate a `Trade` with `min(incoming.qty, resting.qty)` as the fill quantity.
   - Decrement both orders' remaining quantities.
   - If resting order is fully filled, remove it from the deque.
4. Stop when incoming order is fully filled, or no more matching prices exist.

### Complexity

| Operation | Complexity |
|---|---|
| Insert limit order | O(log n) |
| Cancel order | O(log n) amortized |
| Modify order | O(log n) |
| Best bid/ask | O(1) |
| Match market order | O(k log n) where k = fills |
| Get depth (L levels) | O(L) |

---

## Order Types

| Type | Behaviour |
|---|---|
| **Limit** | Rest in book if not immediately marketable |
| **Market** | Execute at best available price; no resting |
| **IOC** (Immediate-or-Cancel) | Fill as much as possible immediately; cancel remainder |
| **FOK** (Fill-or-Kill) | Fill entirely or cancel entirely (no partial fills) |
| **GTC** (Good-Till-Cancel) | Same as Limit; rest indefinitely until filled or cancelled |
