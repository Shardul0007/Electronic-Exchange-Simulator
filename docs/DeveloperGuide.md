# Developer Guide

## Project Structure

```
electronic-exchange-simulator/
├── exchange/
│   ├── interfaces/      # ABCs — contract definitions
│   │   ├── base_book.py      # IOrderBook
│   │   ├── base_engine.py    # IMatchingEngine
│   │   └── base_exchange.py  # IExchange, IMarketDataPublisher, IAnalyticsEngine
│   ├── orders/
│   │   ├── enums.py          # OrderType, OrderSide, OrderStatus, ExecType, etc.
│   │   ├── models.py         # Order, Trade, ExecutionReport dataclasses
│   │   └── validator.py      # OrderValidator, CancelRequestValidator, etc.
│   ├── matching/
│   │   ├── price_level.py    # FIFO deque at a single price
│   │   ├── order_book.py     # LimitOrderBook (SortedDict-based)
│   │   └── engine.py         # MatchingEngine (price-time priority)
│   ├── core/
│   │   ├── exchange.py       # Exchange facade
│   │   ├── market_data.py    # MarketDataPublisher
│   │   └── execution_history.py  # Append-only report log
│   ├── replay/
│   │   ├── loader.py         # CSVReplayLoader
│   │   └── engine.py         # ReplayEngine
│   ├── analytics/
│   │   ├── metrics.py        # Pure analytic functions
│   │   ├── latency.py        # LatencyTracker
│   │   └── flow.py           # OrderFlowAnalyzer
│   ├── reporting/
│   │   └── reporter.py       # ExchangeReporter (JSON/CSV/HTML)
│   └── dashboard/
│       └── app.py            # Plotly Dash application
├── tests/
├── benchmarks/
├── data/
├── docs/
├── examples/
├── reports/
└── templates/
```

---

## Adding a New Order Type

1. Add the enum value to `exchange/orders/enums.py`:
   ```python
   class OrderType(str, Enum):
       MY_NEW_TYPE = "MY_NEW_TYPE"
   ```

2. Add a factory method to `Order` in `exchange/orders/models.py`:
   ```python
   @classmethod
   def create_my_new_type(cls, ...) -> "Order": ...
   ```

3. Add a handler in `MatchingEngine.submit_order()`:
   ```python
   elif order.order_type == OrderType.MY_NEW_TYPE:
       reports = self._handle_my_new_type(order)
   ```

4. Write unit tests in `tests/unit/test_engine.py`.

---

## Adding a New Matching Algorithm

1. Implement `IMatchingEngine` from `exchange/interfaces/base_engine.py`.
2. Create `exchange/matching/pro_rata_engine.py` (for example).
3. Inject it into `Exchange` at construction time:
   ```python
   book = LimitOrderBook("AAPL")
   engine = ProRataEngine(book)
   ex = Exchange(symbol="AAPL", engine=engine)
   ```

The Exchange does not need to change — it only depends on `IMatchingEngine`.

---

## Adding a New Analytics Metric

Analytics are pure functions in `exchange/analytics/metrics.py`:

```python
def compute_my_metric(trades: list[Trade]) -> float | None:
    """Compute something interesting."""
    if not trades:
        return None
    return ...  # your logic
```

Export from `exchange/analytics/__init__.py` and add a unit test.

---

## Extending the Dashboard

The dashboard charts are built in `exchange/dashboard/app.py` as independent
`go.Figure` builders. To add a new panel:

1. Write a `build_my_chart(exchange: Exchange) -> go.Figure` function.
2. Add `dcc.Graph(figure=build_my_chart(exchange))` to the layout.

---

## Running Tests

```bash
# All tests with coverage
pytest tests/ --cov=exchange --cov-report=term-missing

# Specific test file
pytest tests/unit/test_engine.py -v

# Only stress tests
pytest tests/stress/ -v
```

---

## Code Style

- Formatter: `black --line-length 100`
- Imports: `isort --profile black`
- Type checker: `mypy exchange/`
- Linter: `flake8 exchange/ --max-line-length 100`

Run all:
```bash
black exchange/ tests/ examples/ benchmarks/
isort exchange/ tests/ examples/ benchmarks/
mypy exchange/
flake8 exchange/ --max-line-length 100
```

---

## Dependency Injection Pattern

All major components accept dependencies at construction time:

```python
# Default (uses built-in defaults)
ex = Exchange(symbol="AAPL")

# Custom injection (for testing or alternative implementations)
mock_engine = MockMatchingEngine()
mock_history = MockExecutionHistory()
ex = Exchange(symbol="AAPL", engine=mock_engine, history=mock_history)
```

This means every component can be tested in complete isolation using mocks.

---

## Performance Tips

1. **Use INSTANT replay mode** for backtesting — avoids sleep overhead.
2. **Batch order submission** is not yet supported — each order is synchronous.
3. **Reset between simulations** with `ex.reset()` — faster than creating new instances.
4. **Order index lookup** is O(1) — always use `book.get_order(id)` for random access.
5. **Avoid scanning depth** at every tick — call `get_depth()` only when needed.
