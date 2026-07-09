# User Guide

## Getting Started

### Prerequisites

- Python 3.11+
- pip

### Installation

```bash
git clone https://github.com/Shardul0007/Electronic-Exchange-Simulator.git
cd Electronic-Exchange-Simulator

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

---

## Quick Start

### 1. Submit Orders

```python
from exchange.core.exchange import Exchange
from exchange.orders.enums import OrderSide
from exchange.orders.models import Order

ex = Exchange(symbol="AAPL")

# Limit buy at $150.00 for 100 shares
buy = Order.create_limit(side=OrderSide.BUY, price=150.00, quantity=100)
reports = ex.submit_order(buy)

# Limit sell at $150.00 for 50 shares (crosses → fills 50)
sell = Order.create_limit(side=OrderSide.SELL, price=150.00, quantity=50)
reports = ex.submit_order(sell)

print(ex.get_summary())
```

### 2. Market Orders

```python
buy = Order.create_market(side=OrderSide.BUY, quantity=100)
reports = ex.submit_order(buy)
```

### 3. IOC Orders (Immediate-or-Cancel)

```python
ioc = Order.create_ioc(side=OrderSide.BUY, price=150.00, quantity=100)
reports = ex.submit_order(ioc)
# Fills as much as possible, cancels remainder
```

### 4. FOK Orders (Fill-or-Kill)

```python
fok = Order.create_fok(side=OrderSide.SELL, price=150.00, quantity=100)
reports = ex.submit_order(fok)
# Fills entirely or cancels entirely
```

### 5. Cancel an Order

```python
buy = Order.create_limit(OrderSide.BUY, 100.0, 50)
ex.submit_order(buy)
report = ex.cancel_order(buy.order_id)
```

### 6. Modify an Order

```python
buy = Order.create_limit(OrderSide.BUY, 100.0, 100)
ex.submit_order(buy)
report = ex.modify_order(buy.order_id, new_quantity=50, new_price=101.0)
```

---

## Replay Engine

### Replay from CSV

```python
from exchange.replay.engine import ReplayEngine
from exchange.replay.loader import ReplayLoader
from exchange.orders.enums import ReplaySpeed

ex = Exchange(symbol="AAPL")
engine = ReplayEngine(ex)
result = engine.replay_csv("data/sample_orders.csv", speed=ReplaySpeed.INSTANT)
print(f"Replayed {result.orders_submitted} orders in {result.elapsed_seconds:.3f}s")
print(f"Throughput: {result.throughput_per_sec:,.0f} orders/sec")
```

### CSV Format

```csv
order_id,symbol,side,order_type,price,quantity,trader_id,timestamp
<uuid>,AAPL,BUY,LIMIT,100.50,100,trader_01,2024-01-15T09:30:00+00:00
<uuid>,AAPL,SELL,MARKET,,50,trader_02,2024-01-15T09:30:01+00:00
```

Required columns: `side`, `order_type`, `quantity`
Optional: `order_id`, `symbol`, `price` (blank for MARKET), `trader_id`, `timestamp`

---

## Analytics

```python
from exchange.analytics.metrics import (
    compute_vwap, compute_spread, compute_mid_price,
    compute_imbalance_from_depth, compute_price_volatility,
)

trades = ex.get_trades()
depth = ex.get_market_data()

print(f"VWAP:        ${compute_vwap(trades):.4f}")
print(f"Spread:      ${compute_spread(depth['best_bid'], depth['best_ask']):.4f}")
print(f"Mid Price:   ${compute_mid_price(depth['best_bid'], depth['best_ask']):.4f}")
print(f"Imbalance:   {compute_imbalance_from_depth(depth):.4f}")
print(f"Volatility:  {compute_price_volatility(trades):.4f}")
```

---

## Reports

```python
from exchange.reporting.reporter import ExchangeReporter

reporter = ExchangeReporter(ex, output_dir="reports", template_dir="templates")
paths = reporter.generate_all()
# Returns: {"json": "...", "csv": "...", "html": "..."}
print(f"HTML report: {paths['html']}")
```

---

## Dashboard

```bash
python -m exchange.dashboard.app
# Open http://localhost:8050 in your browser
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=exchange --cov-report=html

# Specific suites
pytest tests/unit/       -v
pytest tests/integration/ -v
pytest tests/stress/     -v
pytest tests/replay/     -v
```

---

## Running Benchmarks

```bash
python benchmarks/run_all.py
```

Results are saved to `reports/benchmarks/benchmark_results_<timestamp>.json`.
