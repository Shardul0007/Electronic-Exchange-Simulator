"""
Exchange — the top-level facade coordinating all components.

Implements the Facade pattern: external clients interact only with the
Exchange, which coordinates:
  1. OrderValidator    — input validation (raises ValidationError)
  2. MatchingEngine    — price-time priority matching
  3. ExecutionHistory  — append-only audit log
  4. MarketDataPublisher — L1/L2 snapshot publication

Dependency Injection: all components are passed at construction time,
making the Exchange trivially testable with mock dependencies.

Design note:
  The Exchange does NOT implement business logic (matching, analytics).
  It delegates to specialised components. This keeps the Exchange thin
  and each component independently testable.
"""

from __future__ import annotations

import time
from typing import Any

from exchange.core.execution_history import ExecutionHistory
from exchange.core.market_data import MarketDataPublisher
from exchange.interfaces.base_exchange import IExchange
from exchange.matching.engine import MatchingEngine
from exchange.matching.order_book import LimitOrderBook
from exchange.orders.enums import ExecType
from exchange.orders.models import ExecutionReport, Order
from exchange.orders.validator import (
    CancelRequestValidator,
    ModifyRequestValidator,
    OrderValidator,
    ValidationError,
)


class Exchange(IExchange):
    """
    High-Performance Electronic Exchange.

    Typical usage:
        ex = Exchange(symbol="AAPL")
        reports = ex.submit_order(order)
        data = ex.get_market_data()
    """

    def __init__(
        self,
        symbol: str = "AAPL",
        engine: MatchingEngine | None = None,
        history: ExecutionHistory | None = None,
        publisher: MarketDataPublisher | None = None,
    ) -> None:
        self.symbol: str = symbol

        # Dependency injection with sensible defaults
        book = LimitOrderBook(symbol=symbol)
        self._engine: MatchingEngine = engine or MatchingEngine(book)
        self._history: ExecutionHistory = history or ExecutionHistory()
        self._publisher: MarketDataPublisher = publisher or MarketDataPublisher(symbol)

        # Latency tracking: order_id → submission timestamp (ns)
        self._submit_times: dict[str, int] = {}

        # Latency samples in microseconds
        self._latency_us: list[float] = []

    # -----------------------------------------------------------------------
    # IExchange implementation
    # -----------------------------------------------------------------------

    def submit_order(self, order: Order) -> list[ExecutionReport]:
        """
        Validate and submit an order.

        1. Validate — raise ValidationError on failure (produces REJECTED report).
        2. Match — produce fills, ExecutionReports, Trades.
        3. Record — append to ExecutionHistory.
        4. Publish — push new book snapshot to MarketDataPublisher.
        5. Track latency.

        Returns all ExecutionReports generated for this order.
        """
        t_start_ns = time.perf_counter_ns()
        self._submit_times[order.order_id] = t_start_ns

        try:
            OrderValidator.validate(order)
        except ValidationError as exc:
            reject = ExecutionReport.reject_report(order, reason=exc.reason)
            self._history.record_report(reject)
            return [reject]

        reports = self._engine.submit_order(order)
        self._history.record_reports(reports)

        # Record trades from the engine
        # (trades generated since last check — we track via engine's trade list)
        trades = self._engine.get_trades()
        if trades:
            # Only record new trades (not previously recorded)
            already = self._history.total_trades
            new_trades = trades[already:]
            self._history.record_trades(new_trades)

        # Publish market data
        depth = self._engine.book.get_depth(levels=10)
        self._publisher.publish_snapshot(depth)

        # Track latency
        t_end_ns = time.perf_counter_ns()
        latency_us = (t_end_ns - t_start_ns) / 1_000.0
        self._latency_us.append(latency_us)

        return reports

    def cancel_order(self, order_id: str) -> ExecutionReport | None:
        """Cancel a live order. Returns a cancel report or None."""
        # Retrieve from book for validation
        order = self._engine.book.get_order(order_id)
        if order is None:
            return None

        try:
            CancelRequestValidator.validate(order)
        except ValidationError as exc:
            reject = ExecutionReport.reject_report(order, reason=exc.reason)
            self._history.record_report(reject)
            return reject

        report = self._engine.cancel_order(order_id)
        if report is not None:
            self._history.record_report(report)
            depth = self._engine.book.get_depth(levels=10)
            self._publisher.publish_snapshot(depth)

        return report

    def modify_order(
        self, order_id: str, new_quantity: int, new_price: float | None = None
    ) -> ExecutionReport | None:
        """Modify a live order. Returns a modify report or None."""
        order = self._engine.book.get_order(order_id)
        if order is None:
            return None

        try:
            ModifyRequestValidator.validate(order, new_quantity, new_price)
        except ValidationError as exc:
            reject = ExecutionReport.reject_report(order, reason=exc.reason)
            self._history.record_report(reject)
            return reject

        report = self._engine.modify_order(order_id, new_quantity, new_price)
        if report is not None:
            self._history.record_report(report)
            depth = self._engine.book.get_depth(levels=10)
            self._publisher.publish_snapshot(depth)

        return report

    def get_market_data(self) -> dict:
        """Return the latest L1/L2 snapshot."""
        return self._publisher.get_latest()

    def get_execution_history(self) -> list[ExecutionReport]:
        """Return all ExecutionReports since exchange start."""
        return self._history.all_reports

    # -----------------------------------------------------------------------
    # Additional queries
    # -----------------------------------------------------------------------

    def get_trades(self):
        """Return all trades generated since exchange start."""
        return self._history.all_trades

    def get_summary(self) -> dict:
        """Return execution statistics summary."""
        return self._history.summary()

    def get_latency_stats(self) -> dict:
        """Return latency statistics in microseconds."""
        if not self._latency_us:
            return {}
        samples = sorted(self._latency_us)
        n = len(samples)
        return {
            "count": n,
            "min_us": round(samples[0], 2),
            "max_us": round(samples[-1], 2),
            "mean_us": round(sum(samples) / n, 2),
            "p50_us": round(samples[int(n * 0.50)], 2),
            "p95_us": round(samples[int(n * 0.95)], 2),
            "p99_us": round(samples[int(n * 0.99)], 2),
        }

    @property
    def book(self) -> LimitOrderBook:
        """Direct access to the order book (for analytics/dashboard)."""
        return self._engine.book

    @property
    def engine(self) -> MatchingEngine:
        """Direct access to the matching engine."""
        return self._engine

    @property
    def history(self) -> ExecutionHistory:
        return self._history

    def reset(self) -> None:
        """Reset the exchange to a clean state."""
        self._engine.reset()
        self._history.reset()
        self._publisher.reset()
        self._submit_times.clear()
        self._latency_us.clear()

    def __repr__(self) -> str:
        return (
            f"Exchange({self.symbol}, "
            f"trades={self._history.total_trades}, "
            f"volume={self._history.total_volume})"
        )
