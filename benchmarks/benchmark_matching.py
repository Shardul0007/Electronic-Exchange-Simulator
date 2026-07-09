"""
Matching engine performance benchmarks.

Measures:
  - End-to-end order throughput (orders/sec through the full Exchange)
  - Matching latency distribution (min, p50, p95, p99, max)
  - Replay throughput via ReplayEngine
"""

from __future__ import annotations

import statistics
import time
import random

from exchange.core.exchange import Exchange
from exchange.matching.engine import MatchingEngine
from exchange.matching.order_book import LimitOrderBook
from exchange.orders.enums import OrderSide
from exchange.orders.models import Order
from exchange.replay.engine import ReplayEngine
from exchange.replay.loader import ReplayLoader


def benchmark_exchange_throughput(n: int = 10_000) -> dict:
    """Measure end-to-end exchange throughput."""
    ex = Exchange(symbol="BENCH")
    random.seed(42)

    orders = []
    for i in range(n):
        side = OrderSide.BUY if random.random() > 0.5 else OrderSide.SELL
        price = round(100.0 + random.uniform(-2.0, 2.0), 2)
        qty = random.randint(1, 50) * 10
        orders.append(Order.create_limit(side, price, qty, trader_id=f"t{i % 20}"))

    t_start = time.perf_counter()
    for o in orders:
        ex.submit_order(o)
    t_end = time.perf_counter()

    elapsed = t_end - t_start
    return {
        "operation": "exchange_submit (limit orders)",
        "n": n,
        "elapsed_ms": round(elapsed * 1000, 2),
        "ops_per_sec": round(n / elapsed),
        "ns_per_op": round((elapsed / n) * 1e9, 1),
        "trades_generated": ex.history.total_trades,
    }


def benchmark_matching_latency(n: int = 5_000) -> dict:
    """Measure per-order matching latency."""
    ex = Exchange(symbol="BENCH")
    random.seed(43)
    latencies_us: list[float] = []

    for i in range(n):
        side = OrderSide.BUY if random.random() > 0.5 else OrderSide.SELL
        price = round(100.0 + random.uniform(-2.0, 2.0), 2)
        qty = random.randint(1, 20) * 10
        o = Order.create_limit(side, price, qty)

        t0 = time.perf_counter_ns()
        ex.submit_order(o)
        t1 = time.perf_counter_ns()
        latencies_us.append((t1 - t0) / 1_000.0)

    latencies_us.sort()
    m = len(latencies_us)
    return {
        "operation": "matching latency",
        "n": n,
        "min_us": round(latencies_us[0], 2),
        "p50_us": round(latencies_us[int(m * 0.50)], 2),
        "p95_us": round(latencies_us[int(m * 0.95)], 2),
        "p99_us": round(latencies_us[int(m * 0.99)], 2),
        "max_us": round(latencies_us[-1], 2),
        "mean_us": round(statistics.mean(latencies_us), 2),
    }


def benchmark_replay_throughput(csv_path: str) -> dict:
    """Measure replay engine throughput on the sample dataset."""
    orders = ReplayLoader.load(csv_path)
    ex = Exchange(symbol="BENCH")
    engine = ReplayEngine(ex)

    t_start = time.perf_counter()
    result = engine.replay(orders)
    t_end = time.perf_counter()

    elapsed = t_end - t_start
    return {
        "operation": "replay (1200 orders)",
        "n": len(orders),
        "elapsed_ms": round(elapsed * 1000, 2),
        "ops_per_sec": round(len(orders) / elapsed),
        "trades_generated": result.total_trades,
    }


def run(csv_path: str = "data/sample_orders.csv") -> list[dict]:
    print("\n[BENCH] Matching Engine Benchmarks")
    print("=" * 60)
    results = []

    r1 = benchmark_exchange_throughput(n=10_000)
    results.append(r1)
    print(f"  {'Exchange Throughput':<35} {r1['ops_per_sec']:>10,} orders/sec  "
          f"({r1['ns_per_op']} ns/op)  [{r1['trades_generated']} trades]")

    r2 = benchmark_matching_latency(n=5_000)
    results.append(r2)
    print(f"  {'Matching Latency':<35} "
          f"p50={r2['p50_us']}µs  p95={r2['p95_us']}µs  p99={r2['p99_us']}µs  max={r2['max_us']}µs")

    try:
        r3 = benchmark_replay_throughput(csv_path)
        results.append(r3)
        print(f"  {'Replay Throughput':<35} {r3['ops_per_sec']:>10,} orders/sec  "
              f"[{r3['trades_generated']} trades]")
    except FileNotFoundError:
        print("  [Replay benchmark skipped — sample CSV not found]")

    return results


if __name__ == "__main__":
    run()
