"""
Order book performance benchmarks.

Measures:
  - Insertion throughput (orders/sec)
  - Best bid/ask lookup time
  - Order cancellation throughput
  - Depth query performance
"""

from __future__ import annotations

import statistics
import time
import uuid

from exchange.matching.order_book import LimitOrderBook
from exchange.orders.enums import OrderSide
from exchange.orders.models import Order


def make_order(side: OrderSide, price: float, qty: int = 100) -> Order:
    return Order.create_limit(side=side, price=price, quantity=qty)


def benchmark_insertion(n: int = 50_000) -> dict:
    """Benchmark order insertion into the book."""
    book = LimitOrderBook(symbol="BENCH")
    orders = [
        make_order(
            OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
            round(100.0 + (i % 50) * 0.25, 2),
        )
        for i in range(n)
    ]

    t_start = time.perf_counter()
    for o in orders:
        book.add_order(o)
    t_end = time.perf_counter()

    elapsed = t_end - t_start
    return {
        "operation": "insert",
        "n": n,
        "elapsed_ms": round(elapsed * 1000, 2),
        "ops_per_sec": round(n / elapsed),
        "ns_per_op": round((elapsed / n) * 1e9, 1),
    }


def benchmark_best_bid_ask(n: int = 1_000_000) -> dict:
    """Benchmark O(1) best bid/ask lookup."""
    book = LimitOrderBook(symbol="BENCH")
    for i in range(100):
        book.add_order(make_order(OrderSide.BUY, round(100.0 - i * 0.01, 2)))
        book.add_order(make_order(OrderSide.SELL, round(101.0 + i * 0.01, 2)))

    t_start = time.perf_counter()
    for _ in range(n):
        book.best_bid()
        book.best_ask()
    t_end = time.perf_counter()

    elapsed = t_end - t_start
    total_ops = n * 2
    return {
        "operation": "best_bid_ask",
        "n": total_ops,
        "elapsed_ms": round(elapsed * 1000, 2),
        "ops_per_sec": round(total_ops / elapsed),
        "ns_per_op": round((elapsed / total_ops) * 1e9, 1),
    }


def benchmark_cancellation(n: int = 10_000) -> dict:
    """Benchmark order cancellation."""
    book = LimitOrderBook(symbol="BENCH")
    orders = [make_order(OrderSide.BUY, 100.0) for _ in range(n)]
    for o in orders:
        book.add_order(o)

    t_start = time.perf_counter()
    for o in orders:
        book.cancel_order(o.order_id)
    t_end = time.perf_counter()

    elapsed = t_end - t_start
    return {
        "operation": "cancel",
        "n": n,
        "elapsed_ms": round(elapsed * 1000, 2),
        "ops_per_sec": round(n / elapsed),
        "ns_per_op": round((elapsed / n) * 1e9, 1),
    }


def benchmark_depth_query(n: int = 100_000) -> dict:
    """Benchmark get_depth() call."""
    book = LimitOrderBook(symbol="BENCH")
    for i in range(50):
        book.add_order(make_order(OrderSide.BUY, round(100.0 - i * 0.1, 2)))
        book.add_order(make_order(OrderSide.SELL, round(101.0 + i * 0.1, 2)))

    t_start = time.perf_counter()
    for _ in range(n):
        book.get_depth(10)
    t_end = time.perf_counter()

    elapsed = t_end - t_start
    return {
        "operation": "get_depth(10)",
        "n": n,
        "elapsed_ms": round(elapsed * 1000, 2),
        "ops_per_sec": round(n / elapsed),
        "ns_per_op": round((elapsed / n) * 1e9, 1),
    }


def run() -> list[dict]:
    print("\n[BENCH] Order Book Benchmarks")
    print("=" * 60)
    results = []
    for fn, label in [
        (benchmark_insertion, "Insertion (50k orders)"),
        (benchmark_best_bid_ask, "Best Bid/Ask (1M lookups)"),
        (benchmark_cancellation, "Cancellation (10k orders)"),
        (benchmark_depth_query, "Depth Query (100k calls)"),
    ]:
        r = fn()
        results.append(r)
        print(f"  {label:<35} {r['ops_per_sec']:>10,} ops/sec  ({r['ns_per_op']} ns/op)")
    return results


if __name__ == "__main__":
    run()
