"""
Unit tests for PriceLevel and LimitOrderBook.
"""

import pytest

from exchange.matching.order_book import LimitOrderBook
from exchange.matching.price_level import PriceLevel
from exchange.orders.enums import OrderSide
from exchange.orders.models import Order


def make_limit(
    side: OrderSide = OrderSide.BUY,
    price: float = 100.0,
    qty: int = 100,
    symbol: str = "AAPL",
) -> Order:
    return Order.create_limit(side=side, price=price, quantity=qty, symbol=symbol)


# ===========================================================================
# PriceLevel tests
# ===========================================================================

class TestPriceLevel:
    def test_add_and_peek(self):
        level = PriceLevel(price=100.0)
        o1 = make_limit(qty=50)
        o2 = make_limit(qty=30)
        level.add(o1)
        level.add(o2)
        assert level.peek_front() is o1
        assert level.total_qty == 80

    def test_remove_front_fifo(self):
        level = PriceLevel(price=100.0)
        o1 = make_limit(qty=50)
        o2 = make_limit(qty=30)
        level.add(o1)
        level.add(o2)
        removed = level.remove_front()
        assert removed is o1
        assert level.total_qty == 30
        assert level.order_count == 1

    def test_remove_front_empty_returns_none(self):
        level = PriceLevel(price=100.0)
        assert level.remove_front() is None

    def test_cancel_middle_order(self):
        level = PriceLevel(price=100.0)
        orders = [make_limit(qty=10) for _ in range(5)]
        for o in orders:
            level.add(o)
        target = orders[2]
        result = level.cancel(target.order_id)
        assert result is target
        assert level.order_count == 4
        assert level.total_qty == 40

    def test_cancel_nonexistent_returns_none(self):
        level = PriceLevel(price=100.0)
        level.add(make_limit(qty=10))
        assert level.cancel("nonexistent-id") is None

    def test_is_empty(self):
        level = PriceLevel(price=100.0)
        assert level.is_empty
        level.add(make_limit(qty=10))
        assert not level.is_empty
        level.remove_front()
        assert level.is_empty

    def test_to_dict(self):
        level = PriceLevel(price=100.0)
        level.add(make_limit(qty=50))
        d = level.to_dict()
        assert d["price"] == 100.0
        assert d["total_qty"] == 50
        assert d["order_count"] == 1


# ===========================================================================
# LimitOrderBook tests
# ===========================================================================

class TestLimitOrderBook:
    def setup_method(self):
        self.book = LimitOrderBook(symbol="AAPL")

    def test_empty_book(self):
        assert self.book.best_bid() is None
        assert self.book.best_ask() is None
        assert self.book.spread is None
        assert self.book.mid_price is None
        assert self.book.bid_count == 0
        assert self.book.ask_count == 0

    # --- Insertion ---

    def test_add_bid(self):
        o = make_limit(side=OrderSide.BUY, price=100.0, qty=50)
        self.book.add_order(o)
        assert self.book.best_bid() == 100.0
        assert self.book.bid_count == 1

    def test_add_ask(self):
        o = make_limit(side=OrderSide.SELL, price=101.0, qty=50)
        self.book.add_order(o)
        assert self.book.best_ask() == 101.0
        assert self.book.ask_count == 1

    def test_best_bid_is_highest(self):
        for price in [100.0, 102.0, 101.0, 99.0]:
            self.book.add_order(make_limit(side=OrderSide.BUY, price=price))
        assert self.book.best_bid() == 102.0

    def test_best_ask_is_lowest(self):
        for price in [105.0, 103.0, 104.0, 106.0]:
            self.book.add_order(make_limit(side=OrderSide.SELL, price=price))
        assert self.book.best_ask() == 103.0

    def test_spread_and_mid(self):
        self.book.add_order(make_limit(side=OrderSide.BUY, price=100.0))
        self.book.add_order(make_limit(side=OrderSide.SELL, price=102.0))
        assert self.book.spread == pytest.approx(2.0)
        assert self.book.mid_price == pytest.approx(101.0)

    # --- Cancellation ---

    def test_cancel_existing_order(self):
        o = make_limit(side=OrderSide.BUY, price=100.0, qty=50)
        self.book.add_order(o)
        result = self.book.cancel_order(o.order_id)
        assert result is o
        assert self.book.bid_count == 0
        assert self.book.best_bid() is None

    def test_cancel_nonexistent_returns_none(self):
        result = self.book.cancel_order("nonexistent")
        assert result is None

    def test_cancel_prunes_empty_level(self):
        o = make_limit(side=OrderSide.BUY, price=100.0)
        self.book.add_order(o)
        self.book.cancel_order(o.order_id)
        # The price level at 100.0 should be removed
        assert len(self.book._bids) == 0

    def test_cancel_one_of_multiple_at_same_price(self):
        o1 = make_limit(side=OrderSide.BUY, price=100.0, qty=10)
        o2 = make_limit(side=OrderSide.BUY, price=100.0, qty=20)
        self.book.add_order(o1)
        self.book.add_order(o2)
        self.book.cancel_order(o1.order_id)
        assert self.book.bid_count == 1
        assert self.book.total_bid_qty() == 20

    # --- Order lookup ---

    def test_get_order_finds_existing(self):
        o = make_limit(side=OrderSide.BUY, price=100.0, qty=50)
        self.book.add_order(o)
        found = self.book.get_order(o.order_id)
        assert found is o

    def test_get_order_returns_none_for_unknown(self):
        assert self.book.get_order("unknown-id") is None

    # --- Depth ---

    def test_get_depth_structure(self):
        for price in [100.0, 99.0, 98.0]:
            self.book.add_order(make_limit(side=OrderSide.BUY, price=price))
        for price in [101.0, 102.0, 103.0]:
            self.book.add_order(make_limit(side=OrderSide.SELL, price=price))

        depth = self.book.get_depth(levels=2)
        assert len(depth["bids"]) == 2
        assert len(depth["asks"]) == 2
        assert depth["bids"][0]["price"] == 100.0  # Best bid first
        assert depth["asks"][0]["price"] == 101.0  # Best ask first

    # --- Imbalance ---

    def test_imbalance_empty_book(self):
        assert self.book.imbalance() is None

    def test_imbalance_buy_heavy(self):
        self.book.add_order(make_limit(side=OrderSide.BUY, price=100.0, qty=80))
        self.book.add_order(make_limit(side=OrderSide.SELL, price=101.0, qty=20))
        imb = self.book.imbalance()
        assert imb is not None
        assert imb > 0  # Buy-heavy

    def test_imbalance_balanced(self):
        self.book.add_order(make_limit(side=OrderSide.BUY, price=100.0, qty=50))
        self.book.add_order(make_limit(side=OrderSide.SELL, price=101.0, qty=50))
        assert self.book.imbalance() == pytest.approx(0.0)

    # --- Multiple price levels ---

    def test_multiple_orders_same_price(self):
        for _ in range(5):
            self.book.add_order(make_limit(side=OrderSide.BUY, price=100.0, qty=10))
        assert self.book.bid_count == 5
        assert self.book.total_bid_qty() == 50

    def test_fifo_preserved_at_price_level(self):
        orders = [make_limit(side=OrderSide.BUY, price=100.0, qty=i * 10 + 10)
                  for i in range(5)]
        for o in orders:
            self.book.add_order(o)
        level = self.book.get_level(OrderSide.BUY, 100.0)
        assert level is not None
        assert level.peek_front() is orders[0]  # First in, first out

    # --- Modify ---

    def test_modify_order_quantity(self):
        o = make_limit(side=OrderSide.BUY, price=100.0, qty=100)
        self.book.add_order(o)
        result = self.book.modify_order(o.order_id, new_quantity=50)
        assert result is not None
        assert result.remaining_qty == 50
        assert self.book.total_bid_qty() == 50
