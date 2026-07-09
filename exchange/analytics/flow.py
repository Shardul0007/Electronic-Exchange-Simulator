"""
Order flow statistics.

Tracks and analyses order flow patterns over time:
  - Buy/sell ratio
  - Order arrival rate
  - Size distribution
  - Trader activity
"""

from __future__ import annotations

from collections import Counter, defaultdict

from exchange.orders.enums import ExecType, OrderSide, OrderType
from exchange.orders.models import ExecutionReport, Order, Trade


class OrderFlowAnalyzer:
    """
    Analyses order flow patterns from a sequence of ExecutionReports.

    Provides:
      - Buy/sell order counts and volume
      - Order type distribution
      - Trader activity ranking
      - Arrival rate (orders per second)
      - Size distribution statistics
    """

    def __init__(self) -> None:
        self._reports: list[ExecutionReport] = []
        self._trades: list[Trade] = []

    def ingest_reports(self, reports: list[ExecutionReport]) -> None:
        self._reports.extend(reports)

    def ingest_trades(self, trades: list[Trade]) -> None:
        self._trades.extend(trades)

    def reset(self) -> None:
        self._reports.clear()
        self._trades.clear()

    # ---- Buy/Sell statistics ---------------------------------------------

    def buy_sell_ratio(self) -> dict:
        """Count and volume of buy vs sell orders."""
        buy_count = sell_count = 0
        buy_volume = sell_volume = 0

        for r in self._reports:
            if r.exec_type != ExecType.NEW:
                continue
            if r.order_side == OrderSide.BUY:
                buy_count += 1
                buy_volume += r.order_qty
            else:
                sell_count += 1
                sell_volume += r.order_qty

        total = buy_count + sell_count
        return {
            "buy_count": buy_count,
            "sell_count": sell_count,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "buy_fraction": buy_count / total if total > 0 else None,
            "sell_fraction": sell_count / total if total > 0 else None,
        }

    # ---- Order type distribution -----------------------------------------

    def order_type_distribution(self) -> dict[str, int]:
        """Count of each order type submitted."""
        counts: Counter = Counter()
        for r in self._reports:
            if r.exec_type == ExecType.NEW:
                counts[r.order_type.value] += 1
        return dict(counts)

    # ---- Trader activity -------------------------------------------------

    def top_traders_by_volume(self, top_n: int = 10) -> list[dict]:
        """
        Rank traders by total filled volume.

        Returns list of {'trader_id': str, 'volume': int, 'trades': int}.
        """
        trader_volume: defaultdict[str, int] = defaultdict(int)
        trader_trades: defaultdict[str, int] = defaultdict(int)

        for t in self._trades:
            trader_volume[t.buyer_trader_id] += t.quantity
            trader_trades[t.buyer_trader_id] += 1
            trader_volume[t.seller_trader_id] += t.quantity
            trader_trades[t.seller_trader_id] += 1

        ranked = sorted(trader_volume.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [
            {
                "trader_id": tid,
                "volume": vol,
                "trades": trader_trades[tid],
            }
            for tid, vol in ranked
        ]

    # ---- Size distribution -----------------------------------------------

    def order_size_distribution(self) -> dict:
        """
        Compute order size statistics.

        Returns min, max, mean, median of submitted order quantities.
        """
        import statistics

        sizes = [r.order_qty for r in self._reports if r.exec_type == ExecType.NEW]
        if not sizes:
            return {}
        return {
            "count": len(sizes),
            "min": min(sizes),
            "max": max(sizes),
            "mean": round(statistics.mean(sizes), 2),
            "median": statistics.median(sizes),
            "stdev": round(statistics.stdev(sizes), 2) if len(sizes) > 1 else 0.0,
        }

    # ---- Arrival rate ----------------------------------------------------

    def arrival_rate_per_second(self) -> float | None:
        """
        Estimate order arrival rate (orders per second).

        Uses the time span from first to last NEW report.
        """
        new_reports = [r for r in self._reports if r.exec_type == ExecType.NEW]
        if len(new_reports) < 2:
            return None
        first = new_reports[0].timestamp
        last = new_reports[-1].timestamp
        elapsed = (last - first).total_seconds()
        if elapsed <= 0:
            return None
        return len(new_reports) / elapsed

    # ---- Summary ---------------------------------------------------------

    def summary(self) -> dict:
        return {
            "buy_sell": self.buy_sell_ratio(),
            "type_distribution": self.order_type_distribution(),
            "size_distribution": self.order_size_distribution(),
            "arrival_rate_per_sec": self.arrival_rate_per_second(),
            "top_traders": self.top_traders_by_volume(5),
        }
