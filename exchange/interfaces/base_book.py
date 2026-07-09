"""
Abstract interface for the Order Book.

Defines the contract that all order book implementations must fulfil.
Follows the Interface Segregation Principle — callers depend only on
the minimal surface they need.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exchange.orders.models import Order, PriceLevel


class IOrderBook(ABC):
    """Read/write contract for a limit order book."""

    @abstractmethod
    def add_order(self, order: "Order") -> None:
        """Insert an order into the book."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> "Order | None":
        """Remove an order by ID. Returns the removed order or None."""

    @abstractmethod
    def modify_order(self, order_id: str, new_quantity: int) -> "Order | None":
        """Modify the remaining quantity of an existing order."""

    @abstractmethod
    def best_bid(self) -> "float | None":
        """Return the highest bid price, or None if book is empty."""

    @abstractmethod
    def best_ask(self) -> "float | None":
        """Return the lowest ask price, or None if book is empty."""

    @abstractmethod
    def get_depth(self, levels: int = 10) -> dict:
        """Return up to `levels` price levels on each side."""

    @abstractmethod
    def get_order(self, order_id: str) -> "Order | None":
        """Retrieve a live order by ID."""

    @property
    @abstractmethod
    def bid_count(self) -> int:
        """Number of active bid orders."""

    @property
    @abstractmethod
    def ask_count(self) -> int:
        """Number of active ask orders."""
