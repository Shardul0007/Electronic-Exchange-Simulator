"""
Abstract interface for the Matching Engine.

The engine is responsible for executing orders against the order book
and producing Trade and ExecutionReport objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exchange.orders.models import ExecutionReport, Order, Trade


class IMatchingEngine(ABC):
    """Contract for price-time priority matching engines."""

    @abstractmethod
    def submit_order(self, order: "Order") -> list["ExecutionReport"]:
        """
        Submit an order for matching.

        Returns a list of ExecutionReports (one per fill + one for any
        remaining resting quantity, or a rejection/cancel report).
        """

    @abstractmethod
    def cancel_order(self, order_id: str) -> "ExecutionReport | None":
        """Cancel a live order. Returns a cancel ExecutionReport or None."""

    @abstractmethod
    def modify_order(
        self, order_id: str, new_quantity: int, new_price: float | None = None
    ) -> "ExecutionReport | None":
        """Modify quantity (and optionally price) of a live order."""

    @abstractmethod
    def get_trades(self) -> list["Trade"]:
        """Return all trades generated so far."""

    @abstractmethod
    def reset(self) -> None:
        """Clear the engine state (useful between simulations)."""
