# Design Decisions

## 1. Language: Python 3.11+

**Decision**: Python over C++/Java/Rust.

**Rationale**:
- Primary audience is quant/data engineering internship reviewers who expect Python proficiency.
- Python's `dataclasses`, `abc`, and `typing` modules enable production-quality type-safe designs.
- `sortedcontainers` (pure Python, CPython-optimised) provides O(log n) sorted structures without C extensions.
- The performance gap between Python and C++ is irrelevant at simulation scale; real latency is in the algorithm, not raw CPU cycles.
- Plotly Dash, pandas, and Jinja2 are best-in-class for analytics and reporting in Python.

---

## 2. Price Level Storage: `SortedDict` from `sortedcontainers`

**Decision**: Use `sortedcontainers.SortedDict` keyed by price.

**Alternatives considered**:
- `dict` + `heapq` — O(n) cancellation, O(log n) insert — cancellations are expensive.
- `dict` + manual sorted list — O(n) insert, O(1) min/max — insert is expensive.
- `sortedcontainers.SortedDict` — O(log n) insert, O(log n) delete, O(1) min/max — best all-round.

**Key detail**: Bids are keyed by `-price` so the best bid is always `peekitem(0)`. Asks are keyed by `+price`. This avoids the need for a `max()` scan.

---

## 3. FIFO Queue: `collections.deque`

**Decision**: Each price level stores orders in a `deque`.

**Rationale**:
- O(1) append (new order arrives at back) and O(1) popleft (front order fully fills).
- Cancellation in the middle of a deque is O(n) at that price level, but this is rare and bounded by the number of orders at a single price — acceptable for simulation.
- Real exchanges use intrusive linked lists for O(1) cancel; `deque` is the Python idiomatic approximation.

---

## 4. Order Identity: UUID4

**Decision**: Every order is assigned a UUID4 string as its `order_id`.

**Rationale**:
- Collision-resistant without a central sequence counter.
- Easily serialisable to CSV/JSON.
- In production, exchanges use monotonically increasing 64-bit integers; UUID4 is the Python-safe equivalent for simulation.

---

## 5. Immutable Trades: Frozen Dataclasses

**Decision**: `Trade` objects are `@dataclass(frozen=True)`.

**Rationale**:
- Trades are facts — they should never be mutated after creation.
- Frozen dataclasses are hashable and can be stored in sets or used as dict keys.
- Prevents accidental modification downstream (analytics, reporting).

---

## 6. ExecutionReport Design

**Decision**: A single `ExecutionReport` dataclass covers all lifecycle events (NEW, FILL, PARTIAL_FILL, CANCELLED, REJECTED, MODIFIED).

**Rationale**:
- Mirrors FIX Protocol ExecutionReport (tag 35=8) which uses a single message type with `ExecType` field.
- Simpler downstream processing — callers iterate a list of homogeneous reports.

---

## 7. Matching Engine: Separated from Order Book

**Decision**: `MatchingEngine` and `OrderBook` are separate classes.

**Rationale**:
- Single Responsibility Principle: the book manages state; the engine implements matching logic.
- The book can be independently unit-tested without triggering matching.
- A new matching algorithm (e.g., pro-rata) can be swapped in without touching the book.

---

## 8. Exchange as Facade

**Decision**: `Exchange` is a Facade over `MatchingEngine`, `OrderValidator`, `MarketDataPublisher`, and `ExecutionHistory`.

**Rationale**:
- Clients interact with a single entry point — the exchange — rather than assembling components manually.
- Dependency Injection: all components are injected at construction time, making the exchange easily testable with mock components.

---

## 9. Analytics: Pure Functions

**Decision**: All analytics metrics are implemented as pure functions operating on lists of `Trade` and book snapshots.

**Rationale**:
- Pure functions are stateless and trivially unit-testable.
- No hidden state means metrics are deterministically reproducible — critical for replay correctness.
- Easy to parallelise if performance is needed.

---

## 10. HTML Reports: Jinja2 Templates

**Decision**: HTML report generation uses Jinja2, not f-strings or string concatenation.

**Rationale**:
- Separation of presentation (template) from logic (Python).
- Templates are independently editable without touching Python code.
- Jinja2's autoescaping prevents XSS in generated HTML.

---

## 11. Dashboard: Plotly Dash

**Decision**: Interactive dashboard built with Plotly Dash.

**Alternatives considered**:
- Raw Plotly HTML export — static, no interactivity.
- Bokeh — more complex API, less polished charts.
- Streamlit — higher-level but less control over layout.
- Plotly Dash — React-based, interactive, production-quality, no JavaScript required.

---

## 12. No ML, No Prediction

**Decision**: The project strictly avoids machine learning models.

**Rationale**: The focus is exchange infrastructure — matching, order management, market microstructure. Adding ML would shift complexity away from the core engineering problem and signal a misunderstanding of the domain to quant reviewers.

---

## 13. Test Strategy

| Layer | Tool | What is tested |
|---|---|---|
| Unit | pytest | Individual classes in isolation |
| Integration | pytest | Exchange end-to-end, replay correctness |
| Stress | pytest | 10k+ orders, no crashes, deterministic results |
| Benchmarks | time / statistics | Orders/sec, latency percentiles |

---

## 14. Replay Engine Design

**Decision**: Replay is driven by CSV files with optional timestamp columns.

**Speed modes**:
- `INSTANT` — replay as fast as possible (no sleeps)
- `ACCELERATED` — replay at N× real time
- `REAL_TIME` — replay at 1× real time (honours original timestamps)

**Rationale**: Deterministic replay is the foundation of backtesting systems. By replaying the same CSV, users can reproduce exactly the same execution results — critical for debugging and regression testing.
