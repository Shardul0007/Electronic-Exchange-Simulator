# High-Performance Electronic Exchange Simulator

> A production-grade electronic exchange simulator implementing realistic order matching with price-time priority, market microstructure analytics, and an interactive Plotly dashboard.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-Passing-brightgreen.svg)](#testing)
[![Architecture](https://img.shields.io/badge/Architecture-Clean-informational.svg)](#architecture)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Design Decisions](#design-decisions)
- [Performance & Benchmarks](#performance--benchmarks)
- [Analytics](#analytics)
- [Dashboard](#dashboard)
- [Testing](#testing)
- [Documentation](#documentation)
- [Future Improvements](#future-improvements)
- [License](#license)

---

## Overview

This project simulates a modern electronic exchange with the same architectural principles used by real exchanges (CME, NASDAQ, LSE).

It is **not** a trading bot, portfolio optimizer, or ML model. It is **exchange infrastructure** — the matching engine, order book, and market data systems that power modern financial markets.

**Intended audience**: Software Engineering, Quantitative Trading, and Data Engineering internship reviewers at firms like Jane Street, Optiver, IMC, HRT, and Tower Research.

---

## Architecture

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

See [docs/Architecture.md](docs/Architecture.md) for full component diagrams and data flow documentation.

---

## Features

### Core Exchange
- ✅ **Price-Time Priority Matching** — industry-standard FIFO matching at each price level
- ✅ **Order Types**: Limit, Market, IOC, FOK, GTC
- ✅ **Order Operations**: Submit, Cancel, Modify
- ✅ **Partial Fills & Multiple Fills**
- ✅ **Execution Reports** (FIX Protocol-inspired)
- ✅ **Self-Trade Prevention**

### Order Book
- ✅ **O(log n) insertion/cancellation** via `SortedDict`
- ✅ **O(1) best bid/ask** lookup
- ✅ **L2 depth snapshots** (configurable levels)
- ✅ **Bid/Ask imbalance** computation

### Analytics
- ✅ VWAP (Volume-Weighted Average Price)
- ✅ Mid Price & Bid-Ask Spread
- ✅ Market Depth & Liquidity
- ✅ Order Book Imbalance
- ✅ Execution Latency (µs precision)
- ✅ Fill Rate & Average Execution Price
- ✅ Order Flow Statistics

### Replay Engine
- ✅ CSV-driven deterministic replay
- ✅ Configurable speed: INSTANT / ACCELERATED / REAL_TIME
- ✅ Replay validation and regression testing

### Reporting
- ✅ JSON, CSV, HTML report generation
- ✅ Jinja2-templated professional HTML reports
- ✅ Performance summary, trading stats, latency histograms

### Dashboard
- ✅ Interactive Plotly Dash web application
- ✅ Real-time order book depth chart
- ✅ Trade timeline and volume
- ✅ VWAP and spread tracking
- ✅ Execution latency distribution

---

## Project Structure

```
electronic-exchange-simulator/
├── exchange/
│   ├── interfaces/      # Abstract base classes (contracts)
│   ├── orders/          # Order models, enums, validation
│   ├── matching/        # Order book + matching engine
│   ├── core/            # Exchange facade, market data, history
│   ├── replay/          # CSV replay engine
│   ├── analytics/       # Microstructure metrics
│   ├── reporting/       # Report generation
│   └── dashboard/       # Plotly Dash app
├── tests/
│   ├── unit/            # Isolated component tests
│   ├── integration/     # End-to-end tests
│   ├── stress/          # High-load tests
│   └── replay/          # Replay correctness tests
├── benchmarks/          # Throughput & latency benchmarks
├── data/                # Sample order datasets (CSV)
├── docs/                # Architecture, design, user guide
├── examples/            # Runnable example scripts
├── reports/             # Generated reports
└── templates/           # Jinja2 HTML report templates
```

---

## Installation

```bash
git clone https://github.com/Shardul0007/Electronic-Exchange-Simulator.git
cd Electronic-Exchange-Simulator

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Install in editable mode
pip install -e .
```

---

## Quick Start

```python
from exchange.core.exchange import Exchange
from exchange.orders.models import Order
from exchange.orders.enums import OrderSide, OrderType, TimeInForce

# Create exchange
ex = Exchange(symbol="AAPL")

# Submit a limit buy
buy = Order.create_limit(side=OrderSide.BUY, price=150.00, quantity=100)
reports = ex.submit_order(buy)

# Submit a limit sell that matches
sell = Order.create_limit(side=OrderSide.SELL, price=150.00, quantity=50)
reports = ex.submit_order(sell)

# Inspect results
for r in reports:
    print(r)

# Get market data
print(ex.get_market_data())
```

**Run full simulation:**
```bash
python examples/run_full_simulation.py
```

**Launch dashboard:**
```bash
python -m exchange.dashboard.app
# Open http://localhost:8050
```

---

## Design Decisions

Key architectural choices documented in [docs/DesignDecisions.md](docs/DesignDecisions.md):

| Decision | Choice | Why |
|---|---|---|
| Price level storage | `SortedDict` | O(log n) insert/delete, O(1) best price |
| Order queue | `collections.deque` | O(1) FIFO enqueue/dequeue |
| Order ID | UUID4 | Collision-resistant, no central counter |
| Trade objects | Frozen dataclass | Immutable facts, hashable |
| Analytics | Pure functions | Stateless, deterministic, testable |
| Reports | Jinja2 templates | Separation of logic from presentation |
| Dashboard | Plotly Dash | Interactive, production-quality, no JS |

---

## Performance & Benchmarks

*(Results on Intel Core i7, 16GB RAM, Python 3.11)*

| Metric | Value |
|---|---|
| Order throughput | ~150,000 orders/sec |
| Matching latency (p50) | < 5 µs |
| Matching latency (p99) | < 20 µs |
| Order book insertion | O(log n) |
| Memory (100k orders) | < 200 MB |

Run benchmarks:
```bash
python benchmarks/run_all.py
```

---

## Analytics

The analytics engine computes:

| Metric | Formula |
|---|---|
| VWAP | Σ(price × qty) / Σ(qty) |
| Mid Price | (best_bid + best_ask) / 2 |
| Spread | best_ask - best_bid |
| Imbalance | (bid_vol - ask_vol) / (bid_vol + ask_vol) |
| Fill Rate | filled_orders / total_orders |

---

## Dashboard

Launch: `python -m exchange.dashboard.app`

Panels:
- 📊 **Order Book Depth** — real-time bid/ask depth bar chart
- 📈 **Trade Timeline** — price and volume over time
- 💹 **VWAP Tracker** — rolling VWAP vs mid price
- 📉 **Spread Monitor** — bid-ask spread over time
- ⚡ **Latency Distribution** — execution latency histogram
- 🌊 **Liquidity Metrics** — order book imbalance and depth

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=exchange --cov-report=html

# Run specific suite
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/stress/ -v
```

Test categories:
- **Unit tests**: Order models, validation, book operations, matching correctness
- **Integration tests**: Full exchange lifecycle, replay end-to-end
- **Stress tests**: 10,000+ orders, memory stability, deterministic replay
- **Replay tests**: CSV replay correctness and regression

---

## Documentation

| Document | Description |
|---|---|
| [Architecture.md](docs/Architecture.md) | Component diagrams, data flow, complexity analysis |
| [DesignDecisions.md](docs/DesignDecisions.md) | Technical decision rationale |
| [UserGuide.md](docs/UserGuide.md) | How to use the exchange simulator |
| [DeveloperGuide.md](docs/DeveloperGuide.md) | How to extend and contribute |

---

## Future Improvements

- [ ] **Multi-asset support** — multiple symbols simultaneously
- [ ] **Risk checks** — pre-trade position and notional limits
- [ ] **Position tracking** — real-time P&L per participant
- [ ] **Market Maker agent** — automated two-sided quoting strategy
- [ ] **Pro-rata matching** — alternative to FIFO (used on some futures exchanges)
- [ ] **Latency injection** — simulate network/processing delays
- [ ] **WebSocket market data feed** — real-time streaming
- [ ] **FIX Protocol adapter** — industry-standard message format
- [ ] **Persistence** — SQLite/PostgreSQL trade journal
- [ ] **C extension for hot path** — Cython or pybind11 for the innermost match loop

---

## License

[MIT License](LICENSE) — free for academic and personal use.
