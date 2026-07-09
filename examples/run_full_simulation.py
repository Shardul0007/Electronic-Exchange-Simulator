"""
Full simulation example — runs a complete exchange session and generates reports.

Usage:
    python examples/run_full_simulation.py

This script demonstrates:
  1. Bootstrapping the exchange
  2. Loading and replaying 1200 orders from CSV
  3. Computing analytics metrics
  4. Generating JSON, CSV, and HTML reports
  5. Printing a performance summary
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from exchange.analytics.flow import OrderFlowAnalyzer
from exchange.analytics.latency import LatencyTracker
from exchange.analytics.metrics import (
    compute_imbalance_from_depth,
    compute_price_volatility,
    compute_rolling_vwap,
    compute_vwap,
)
from exchange.core.exchange import Exchange
from exchange.orders.enums import OrderSide, ReplaySpeed
from exchange.replay.engine import ReplayEngine
from exchange.replay.loader import ReplayLoader
from exchange.reporting.reporter import ExchangeReporter


def main() -> None:
    print("\n" + "=" * 65)
    print("  HIGH-PERFORMANCE ELECTRONIC EXCHANGE SIMULATOR")
    print("  Full Simulation - AAPL")
    print("=" * 65)

    # ---- 1. Bootstrap exchange ---------------------------------------------
    ex = Exchange(symbol="AAPL")
    print("\n[OK] Exchange initialised (symbol=AAPL)")

    # ---- 2. Load sample orders ---------------------------------------------
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "sample_orders.csv")
    orders = ReplayLoader.load(csv_path)
    print(f"[OK] Loaded {len(orders)} orders from {csv_path}")

    # ---- 3. Replay ---------------------------------------------------------
    replay_engine = ReplayEngine(ex)
    result = replay_engine.replay(orders, speed=ReplaySpeed.INSTANT)
    print(f"[OK] Replayed {result.orders_submitted:,} orders in {result.elapsed_seconds:.3f}s")
    print(f"     Throughput:     {result.throughput_per_sec:,.0f} orders/sec")
    print(f"     Trades:         {result.total_trades:,}")
    print(f"     Volume:         {result.total_volume:,} shares")
    print(f"     Notional:       ${result.total_notional:,.2f}")

    # ---- 4. Analytics ------------------------------------------------------
    trades = ex.get_trades()
    depth = ex.get_market_data()

    vwap = compute_vwap(trades)
    volatility = compute_price_volatility(trades)
    imbalance = compute_imbalance_from_depth(depth)

    print(f"\n[ANALYTICS]:")
    print(f"  VWAP:             ${vwap:.4f}" if vwap else "  VWAP:             N/A")
    print(f"  Best Bid:         ${depth.get('best_bid', 'N/A')}")
    print(f"  Best Ask:         ${depth.get('best_ask', 'N/A')}")
    print(f"  Spread:           ${depth.get('spread', 'N/A')}")
    print(f"  Mid Price:        ${depth.get('mid_price', 'N/A')}")
    print(f"  Volatility:       {volatility:.4f}" if volatility else "  Volatility:       N/A")
    print(f"  Book Imbalance:   {imbalance:.4f}" if imbalance else "  Book Imbalance:   N/A")

    # ---- 5. Latency stats --------------------------------------------------
    latency = ex.get_latency_stats()
    if latency:
        print(f"\n[LATENCY] (per order submission):")
        print(f"  P50:  {latency.get('p50_us')} us")
        print(f"  P95:  {latency.get('p95_us')} us")
        print(f"  P99:  {latency.get('p99_us')} us")
        print(f"  Max:  {latency.get('max_us')} us")

    # ---- 6. Order flow -----------------------------------------------------
    flow = OrderFlowAnalyzer()
    flow.ingest_reports(ex.get_execution_history())
    flow.ingest_trades(trades)
    bs = flow.buy_sell_ratio()
    print(f"\n[ORDER FLOW]:")
    print(f"  Buy orders:  {bs['buy_count']:,}  ({bs.get('buy_fraction', 0)*100:.1f}%)")
    print(f"  Sell orders: {bs['sell_count']:,}  ({bs.get('sell_fraction', 0)*100:.1f}%)")
    top = flow.top_traders_by_volume(3)
    if top:
        print(f"  Top traders: {', '.join(t['trader_id'] for t in top)}")

    # ---- 7. Generate reports -----------------------------------------------
    reporter = ExchangeReporter(
        ex,
        output_dir="reports",
        template_dir="templates",
    )
    paths = reporter.generate_all()
    print(f"\n[REPORTS] generated:")
    for fmt, path in paths.items():
        print(f"  {fmt.upper()}: {path}")

    # ---- 8. Summary --------------------------------------------------------
    summary = ex.get_summary()
    print(f"\n[DONE] Simulation complete.")
    print(f"   Fill rate: {summary['fill_rate']*100:.1f}%  |  "
          f"Rejection rate: {summary['rejection_rate']*100:.1f}%  |  "
          f"Total trades: {summary['total_trades']:,}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
