"""
Abstract interface for the Exchange.

The Exchange is the top-level facade that coordinates order routing,
validation, matching, market data publication, and execution history.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exchange.orders.models import ExecutionReport, Order


class IExchange(ABC):
    """Top-level exchange contract."""

    @abstractmethod
    def submit_order(self, order: "Order") -> list["ExecutionReport"]:
        """Validate and route an order to the matching engine."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> "ExecutionReport | None":
        """Request cancellation of a live order."""

    @abstractmethod
    def modify_order(
        self, order_id: str, new_quantity: int, new_price: float | None = None
    ) -> "ExecutionReport | None":
        """Request modification of a live order."""

    @abstractmethod
    def get_market_data(self) -> dict:
        """Return current L1/L2 market data snapshot."""

    @abstractmethod
    def get_execution_history(self) -> list["ExecutionReport"]:
        """Return all execution reports produced since exchange start."""


class IMarketDataPublisher(ABC):
    """Contract for market data feed components."""

    @abstractmethod
    def publish_snapshot(self, depth: dict) -> None:
        """Publish an order book depth snapshot."""

    @abstractmethod
    def get_latest(self) -> dict:
        """Return the most recent published snapshot."""


class IAnalyticsEngine(ABC):
    """Contract for analytics computation components."""

    @abstractmethod
    def compute_vwap(self) -> float | None:
        """Volume-weighted average price of all trades."""

    @abstractmethod
    def compute_spread(self) -> float | None:
        """Current bid-ask spread."""

    @abstractmethod
    def compute_mid_price(self) -> float | None:
        """Current mid price ((best_bid + best_ask) / 2)."""

    @abstractmethod
    def compute_imbalance(self) -> float | None:
        """Order book imbalance [-1.0, +1.0]."""
