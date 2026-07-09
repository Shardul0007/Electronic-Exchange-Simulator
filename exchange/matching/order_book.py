"""
Limit Order Book.

Implements a two-sided order book (bids and asks) using price-time priority.

Data structures:
  - Bids: SortedDict keyed by -price (so index 0 = best/highest bid)
  - Asks: SortedDict keyed by +price (so index 0 = best/lowest ask)
  - Both sides map price → PriceLevel (deque of Orders at that price)
  - A flat dict `_order_index` maps order_id → (side, price) for O(1) lookups

Complexity:
  | Operation       | Complexity        |
  |-----------------|-------------------|
  | add_order       | O(log n)          |
  | cancel_order    | O(log n) amortised|
  | best_bid/ask    | O(1)              |
  | get_depth       | O(L)              |
  | get_order       | O(1)              |
"""

from __future__ import annotations

from sortedcontainers import SortedDict  # type: ignore

from exchange.interfaces.base_book import IOrderBook
from exchange.matching.price_level import PriceLevel
from exchange.orders.enums import OrderSide
from exchange.orders.models import Order


class LimitOrderBook(IOrderBook):
    """
    Two-sided limit order book with O(log n) insert/cancel and O(1) best price.

    Key design details:
    - Bids keyed by -price so SortedDict.peekitem(0) returns the best bid.
    - Asks keyed by +price so SortedDict.peekitem(0) returns the best ask.
    - Empty price levels are pruned immediately to keep the book clean.
    - `_order_index` provides O(1) order lookup without scanning price levels.
    """

    def __init__(self, symbol: str = "AAPL") -> None:
        self.symbol: str = symbol

        # Bids: keyed by -price (descending) → PriceLevel
        self._bids: SortedDict = SortedDict()
        # Asks: keyed by +price (ascending) → PriceLevel
        self._asks: SortedDict = SortedDict()

        # order_id → (side, price_key) for O(1) lookup
        self._order_index: dict[str, tuple[OrderSide, float]] = {}

    # -----------------------------------------------------------------------
    # IOrderBook implementation
    # -----------------------------------------------------------------------

    def add_order(self, order: Order) -> None:
        """Insert a resting limit order into the book."""
        if order.price is None:
            raise ValueError(f"Cannot add market order {order.order_id} to book")

        book = self._get_book(order.side)
        key = self._price_key(order.side, order.price)

        if key not in book:
            book[key] = PriceLevel(price=order.price)

        book[key].add(order)
        self._order_index[order.order_id] = (order.side, key)

    def cancel_order(self, order_id: str) -> Order | None:
        """Remove an order from the book. Returns the removed order or None."""
        if order_id not in self._order_index:
            return None

        side, key = self._order_index.pop(order_id)
        book = self._get_book(side)

        if key not in book:
            return None

        level: PriceLevel = book[key]
        order = level.cancel(order_id)

        if order is not None and level.is_empty:
            del book[key]

        return order

    def modify_order(self, order_id: str, new_quantity: int) -> Order | None:
        """
        Modify the remaining quantity of an existing order.

        Note: This implementation does NOT reset time priority (no re-queue).
        A true price change would require cancel + re-insert, handled by the engine.
        """
        if order_id not in self._order_index:
            return None

        side, key = self._order_index[order_id]
        book = self._get_book(side)

        if key not in book:
            return None

        level: PriceLevel = book[key]
        for order in level._orders:
            if order.order_id == order_id:
                delta = order.remaining_qty - new_quantity
                order.remaining_qty = new_quantity
                level._total_qty -= delta
                return order

        return None

    def best_bid(self) -> float | None:
        """Highest active bid price, or None."""
        if not self._bids:
            return None
        key, level = self._bids.peekitem(0)
        return level.price

    def best_ask(self) -> float | None:
        """Lowest active ask price, or None."""
        if not self._asks:
            return None
        key, level = self._asks.peekitem(0)
        return level.price

    def get_depth(self, levels: int = 10) -> dict:
        """
        Return up to `levels` price levels on each side.

        Returns a dict with keys 'bids' and 'asks', each a list of
        {'price': float, 'total_qty': int, 'order_count': int} dicts.
        """
        bids = [
            level.to_dict()
            for _, level in self._bids.items()
        ][:levels]

        asks = [
            level.to_dict()
            for _, level in self._asks.items()
        ][:levels]

        return {
            "symbol": self.symbol,
            "bids": bids,
            "asks": asks,
            "best_bid": self.best_bid(),
            "best_ask": self.best_ask(),
            "spread": self.spread,
            "mid_price": self.mid_price,
        }

    def get_order(self, order_id: str) -> Order | None:
        """Retrieve a live order by ID without removing it. O(1) lookup."""
        if order_id not in self._order_index:
            return None

        side, key = self._order_index[order_id]
        book = self._get_book(side)

        if key not in book:
            return None

        level: PriceLevel = book[key]
        for order in level._orders:
            if order.order_id == order_id:
                return order

        return None

    @property
    def bid_count(self) -> int:
        """Total number of active bid orders."""
        return sum(level.order_count for level in self._bids.values())

    @property
    def ask_count(self) -> int:
        """Total number of active ask orders."""
        return sum(level.order_count for level in self._asks.values())

    # -----------------------------------------------------------------------
    # Additional book-specific methods
    # -----------------------------------------------------------------------

    @property
    def spread(self) -> float | None:
        """Bid-ask spread. None if either side is empty."""
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return round(ask - bid, 10)

    @property
    def mid_price(self) -> float | None:
        """Mid price. None if either side is empty."""
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2.0

    def total_bid_qty(self) -> int:
        """Total quantity on the bid side."""
        return sum(level.total_qty for level in self._bids.values())

    def total_ask_qty(self) -> int:
        """Total quantity on the ask side."""
        return sum(level.total_qty for level in self._asks.values())

    def imbalance(self) -> float | None:
        """
        Order book imbalance in [-1, +1].

        +1 means all volume is on the bid side (strong buy pressure).
        -1 means all volume is on the ask side (strong sell pressure).
        """
        bid_vol = self.total_bid_qty()
        ask_vol = self.total_ask_qty()
        total = bid_vol + ask_vol
        if total == 0:
            return None
        return (bid_vol - ask_vol) / total

    def get_level(self, side: OrderSide, price: float) -> PriceLevel | None:
        """Return the PriceLevel at a given price/side, or None."""
        book = self._get_book(side)
        key = self._price_key(side, price)
        return book.get(key)

    def get_best_level(self, side: OrderSide) -> PriceLevel | None:
        """Return the best PriceLevel for the given side, or None."""
        book = self._get_book(side)
        if not book:
            return None
        _, level = book.peekitem(0)
        return level

    def is_empty(self) -> bool:
        """True if both sides of the book are empty."""
        return not self._bids and not self._asks

    def __repr__(self) -> str:
        return (
            f"LimitOrderBook({self.symbol}, "
            f"bids={self.bid_count}, asks={self.ask_count}, "
            f"best_bid={self.best_bid()}, best_ask={self.best_ask()})"
        )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _get_book(self, side: OrderSide) -> SortedDict:
        return self._bids if side == OrderSide.BUY else self._asks

    @staticmethod
    def _price_key(side: OrderSide, price: float) -> float:
        """
        Convert a price to a sort key.

        Bids are negated so SortedDict.peekitem(0) returns the highest bid.
        Asks are stored as-is so peekitem(0) returns the lowest ask.
        """
        return -price if side == OrderSide.BUY else price
