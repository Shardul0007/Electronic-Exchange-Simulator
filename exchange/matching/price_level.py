"""
Price level: a FIFO queue of orders at a single price.

Design:
  - Uses `collections.deque` for O(1) append (new order) and O(1) popleft (front fills).
  - Cancellation within the deque is O(n) at that price level, which is acceptable
    in simulation where most cancels target recently-added orders.
  - In production systems (C++), a doubly-linked list with an O(1) node pointer
    lookup in a hash map would be used for O(1) cancel.

This class is deliberately thin — it only manages the queue at one price.
The OrderBook owns the SortedDict of PriceLevels.
"""

from __future__ import annotations

from collections import deque

from exchange.orders.models import Order


class PriceLevel:
    """
    A FIFO queue of orders resting at one specific price.

    All orders in a single PriceLevel have the same price.
    Time priority is maintained by insertion order (deque).
    """

    __slots__ = ("price", "_orders", "_total_qty")

    def __init__(self, price: float) -> None:
        self.price: float = price
        self._orders: deque[Order] = deque()
        self._total_qty: int = 0

    # ---- Mutations --------------------------------------------------------

    def add(self, order: Order) -> None:
        """Append an order to the back of the queue (lowest time priority)."""
        self._orders.append(order)
        self._total_qty += order.remaining_qty

    def remove_front(self) -> Order | None:
        """
        Remove and return the front order (highest time priority).
        Returns None if empty.
        """
        if not self._orders:
            return None
        order = self._orders.popleft()
        self._total_qty -= order.remaining_qty
        return order

    def peek_front(self) -> Order | None:
        """Return (do not remove) the front order, or None if empty."""
        return self._orders[0] if self._orders else None

    def cancel(self, order_id: str) -> Order | None:
        """
        Remove an order by ID from anywhere in the queue.

        O(n) at this price level — acceptable for simulation.
        Returns the cancelled order or None if not found.
        """
        for i, order in enumerate(self._orders):
            if order.order_id == order_id:
                del self._orders[i]
                self._total_qty -= order.remaining_qty
                return order
        return None

    def reduce_qty(self, qty: int) -> None:
        """Reduce total qty tracker after a partial fill at the front."""
        self._total_qty = max(0, self._total_qty - qty)

    # ---- Queries ----------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return len(self._orders) == 0

    @property
    def total_qty(self) -> int:
        """Total quantity of all orders resting at this price level."""
        return self._total_qty

    @property
    def order_count(self) -> int:
        """Number of orders at this price level."""
        return len(self._orders)

    def to_dict(self) -> dict:
        """Serialise to a dict suitable for L2 depth snapshots."""
        return {
            "price": self.price,
            "total_qty": self._total_qty,
            "order_count": len(self._orders),
        }

    def __len__(self) -> int:
        return len(self._orders)

    def __repr__(self) -> str:
        return f"PriceLevel(price={self.price}, qty={self._total_qty}, orders={len(self._orders)})"
