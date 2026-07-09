"""
Replay Engine — deterministic historical order replay.

Replays a sequence of Orders (from CSV or in-memory) through the Exchange,
supporting three speed modes:

  INSTANT     — replay at maximum speed (no sleeps; useful for backtesting)
  ACCELERATED — replay at N× real-time speed (honours timestamps)
  REAL_TIME   — replay at 1× real-time speed (honours timestamps exactly)

Design:
  - The engine is stateless between replays (replay() can be called multiple times).
  - It accepts the Exchange as a dependency (Dependency Injection).
  - Results are returned as a ReplayResult containing all trades and reports.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from exchange.core.exchange import Exchange
from exchange.orders.enums import ReplaySpeed
from exchange.orders.models import ExecutionReport, Order, Trade
from exchange.replay.loader import ReplayLoader


@dataclass
class ReplayResult:
    """Aggregated results from a single replay run."""

    orders_submitted: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    orders_cancelled: int = 0

    total_trades: int = 0
    total_volume: int = 0
    total_notional: float = 0.0

    elapsed_seconds: float = 0.0
    throughput_per_sec: float = 0.0

    all_reports: list[ExecutionReport] = field(default_factory=list)
    all_trades: list[Trade] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "orders_submitted": self.orders_submitted,
            "orders_filled": self.orders_filled,
            "orders_rejected": self.orders_rejected,
            "orders_cancelled": self.orders_cancelled,
            "total_trades": self.total_trades,
            "total_volume": self.total_volume,
            "total_notional": round(self.total_notional, 4),
            "vwap": (
                round(self.total_notional / self.total_volume, 4)
                if self.total_volume > 0 else None
            ),
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "throughput_per_sec": round(self.throughput_per_sec, 2),
        }


class ReplayEngine:
    """
    Deterministic order replay engine.

    Feeds a sequence of Orders into the Exchange and collects results.
    Useful for backtesting, regression testing, and performance benchmarking.
    """

    def __init__(
        self,
        exchange: Exchange,
        on_order_submitted: Callable[[Order, list[ExecutionReport]], None] | None = None,
    ) -> None:
        self._exchange: Exchange = exchange
        self._on_order_submitted = on_order_submitted  # Optional callback

    # -----------------------------------------------------------------------
    # Replay from CSV file
    # -----------------------------------------------------------------------

    def replay_csv(
        self,
        path: str,
        speed: ReplaySpeed = ReplaySpeed.INSTANT,
        acceleration: float = 10.0,
        reset_exchange: bool = True,
    ) -> ReplayResult:
        """
        Load orders from CSV and replay them.

        Args:
            path: Path to the CSV file.
            speed: INSTANT, ACCELERATED, or REAL_TIME.
            acceleration: Multiplier for ACCELERATED mode (default 10×).
            reset_exchange: If True, reset exchange state before replay.
        """
        if speed == ReplaySpeed.INSTANT:
            orders = ReplayLoader.load(path)
            return self.replay(orders, speed=speed, reset_exchange=reset_exchange)
        else:
            timed_orders = ReplayLoader.load_with_timestamps(path)
            return self._replay_timed(timed_orders, speed, acceleration, reset_exchange)

    # -----------------------------------------------------------------------
    # Replay from in-memory list
    # -----------------------------------------------------------------------

    def replay(
        self,
        orders: list[Order],
        speed: ReplaySpeed = ReplaySpeed.INSTANT,
        reset_exchange: bool = True,
    ) -> ReplayResult:
        """
        Replay a list of orders through the exchange.

        Uses INSTANT mode (no timing). For timing-aware replay, use replay_csv.
        """
        if reset_exchange:
            self._exchange.reset()

        result = ReplayResult()
        t_start = time.perf_counter()

        for order in orders:
            reports = self._exchange.submit_order(order)
            self._process_reports(order, reports, result)

        t_end = time.perf_counter()
        self._finalise(result, t_start, t_end)
        return result

    # -----------------------------------------------------------------------
    # Timing-aware replay
    # -----------------------------------------------------------------------

    def _replay_timed(
        self,
        timed_orders: list[tuple[datetime | None, Order]],
        speed: ReplaySpeed,
        acceleration: float,
        reset_exchange: bool,
    ) -> ReplayResult:
        """Replay with timing honours (REAL_TIME or ACCELERATED)."""
        if reset_exchange:
            self._exchange.reset()

        result = ReplayResult()
        t_start = time.perf_counter()
        wall_start = time.perf_counter()

        # Find first timestamp to establish a reference point
        first_ts: datetime | None = next(
            (ts for ts, _ in timed_orders if ts is not None), None
        )

        for ts, order in timed_orders:
            if ts is not None and first_ts is not None:
                # How far into the sequence should we be?
                sim_offset_sec = (ts - first_ts).total_seconds()
                target_wall_offset = sim_offset_sec / (
                    acceleration if speed == ReplaySpeed.ACCELERATED else 1.0
                )
                wall_elapsed = time.perf_counter() - wall_start
                sleep_duration = target_wall_offset - wall_elapsed
                if sleep_duration > 0:
                    time.sleep(sleep_duration)

            reports = self._exchange.submit_order(order)
            self._process_reports(order, reports, result)

        t_end = time.perf_counter()
        self._finalise(result, t_start, t_end)
        return result

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _process_reports(
        order: Order, reports: list[ExecutionReport], result: ReplayResult
    ) -> None:
        from exchange.orders.enums import ExecType
        result.orders_submitted += 1
        result.all_reports.extend(reports)

        for r in reports:
            if r.exec_type == ExecType.REJECTED:
                result.orders_rejected += 1
            elif r.exec_type == ExecType.CANCELLED:
                result.orders_cancelled += 1
            elif r.exec_type in (ExecType.FILL, ExecType.PARTIAL_FILL):
                if r.exec_type == ExecType.FILL:
                    result.orders_filled += 1
                result.total_trades += 1
                result.total_volume += r.last_fill_qty
                result.total_notional += r.last_fill_qty * r.last_fill_price

    @staticmethod
    def _finalise(result: ReplayResult, t_start: float, t_end: float) -> None:
        result.elapsed_seconds = t_end - t_start
        if result.elapsed_seconds > 0:
            result.throughput_per_sec = result.orders_submitted / result.elapsed_seconds
