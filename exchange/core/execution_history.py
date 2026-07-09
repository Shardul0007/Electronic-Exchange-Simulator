"""
Execution history — persistent log of all ExecutionReports.

Provides querying, serialisation, and statistics over the
complete record of order lifecycle events.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from exchange.orders.enums import ExecType, OrderSide
from exchange.orders.models import ExecutionReport, Trade


class ExecutionHistory:
    """
    Maintains an append-only log of ExecutionReports and Trades.

    Provides query methods for reporting and analytics.
    """

    def __init__(self) -> None:
        self._reports: list[ExecutionReport] = []
        self._trades: list[Trade] = []

    # ---- Write -------------------------------------------------------

    def record_reports(self, reports: list[ExecutionReport]) -> None:
        """Append a batch of ExecutionReports."""
        self._reports.extend(reports)

    def record_report(self, report: ExecutionReport) -> None:
        """Append a single ExecutionReport."""
        self._reports.append(report)

    def record_trade(self, trade: Trade) -> None:
        """Append a trade record."""
        self._trades.append(trade)

    def record_trades(self, trades: list[Trade]) -> None:
        """Append a batch of trades."""
        self._trades.extend(trades)

    # ---- Query -------------------------------------------------------

    @property
    def all_reports(self) -> list[ExecutionReport]:
        return list(self._reports)

    @property
    def all_trades(self) -> list[Trade]:
        return list(self._trades)

    def reports_for_order(self, order_id: str) -> list[ExecutionReport]:
        return [r for r in self._reports if r.order_id == order_id]

    def trades_for_order(self, order_id: str) -> list[Trade]:
        return [
            t for t in self._trades
            if t.buy_order_id == order_id or t.sell_order_id == order_id
        ]

    def fill_reports(self) -> list[ExecutionReport]:
        """All FILL and PARTIAL_FILL reports."""
        return [
            r for r in self._reports
            if r.exec_type in (ExecType.FILL, ExecType.PARTIAL_FILL)
        ]

    def rejected_reports(self) -> list[ExecutionReport]:
        return [r for r in self._reports if r.exec_type == ExecType.REJECTED]

    def cancelled_reports(self) -> list[ExecutionReport]:
        return [r for r in self._reports if r.exec_type == ExecType.CANCELLED]

    # ---- Statistics --------------------------------------------------

    @property
    def total_orders(self) -> int:
        """Count of unique submitted order IDs."""
        return len({r.order_id for r in self._reports})

    @property
    def total_trades(self) -> int:
        return len(self._trades)

    @property
    def total_volume(self) -> int:
        return sum(t.quantity for t in self._trades)

    @property
    def total_notional(self) -> float:
        return sum(t.notional for t in self._trades)

    @property
    def fill_rate(self) -> float:
        """Fraction of submitted orders that received at least one fill."""
        total = self.total_orders
        if total == 0:
            return 0.0
        filled_ids = {
            r.order_id for r in self._reports
            if r.exec_type in (ExecType.FILL, ExecType.PARTIAL_FILL)
        }
        return len(filled_ids) / total

    @property
    def rejection_rate(self) -> float:
        total = self.total_orders
        if total == 0:
            return 0.0
        return len(self.rejected_reports()) / total

    def summary(self) -> dict:
        """Return a summary statistics dict."""
        vwap = self.total_notional / self.total_volume if self.total_volume > 0 else None
        return {
            "total_orders": self.total_orders,
            "total_trades": self.total_trades,
            "total_volume": self.total_volume,
            "total_notional": round(self.total_notional, 4),
            "vwap": round(vwap, 4) if vwap is not None else None,
            "fill_rate": round(self.fill_rate, 4),
            "rejection_rate": round(self.rejection_rate, 4),
            "rejected_orders": len(self.rejected_reports()),
            "cancelled_orders": len(self.cancelled_reports()),
        }

    def reset(self) -> None:
        self._reports.clear()
        self._trades.clear()
