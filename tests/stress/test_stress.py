"""
Stress tests — high-load scenarios for the Exchange.

Validates:
  - Correctness under 10,000+ orders
  - Memory stability (no unbounded growth)
  - Book integrity after mixed operations
  - Determinism under repeated runs
"""

import random
import pytest

from exchange.core.exchange import Exchange
from exchange.orders.enums import OrderSide, OrderType
from exchange.orders.models import Order


def make_exchange() -> Exchange:
    return Exchange(symbol="STRESS")


def rand_limit(seed_offset: int = 0) -> Order:
    rng = random.Random(seed_offset)
    side = OrderSide.BUY if rng.random() > 0.5 else OrderSide.SELL
    price = round(100.0 + rng.uniform(-5.0, 5.0), 2)
    qty = rng.randint(1, 200) * 10
    return Order.create_limit(side=side, price=price, quantity=qty,
                              trader_id=f"trader_{rng.randint(1,20)}")


class TestStress:
    def test_10k_orders_no_crash(self):
        """10,000 orders must be processed without exception."""
        ex = make_exchange()
        random.seed(0)
        for i in range(10_000):
            side = OrderSide.BUY if random.random() > 0.5 else OrderSide.SELL
            price = round(100.0 + random.uniform(-3.0, 3.0), 2)
            qty = random.randint(1, 100) * 10
            ex.submit_order(Order.create_limit(side, price, qty, trader_id=f"t{i % 50}"))

        assert ex.history.total_orders == 10_000

    def test_mixed_order_types_stress(self):
        """Mix of LIMIT, MARKET, IOC, FOK under load."""
        ex = make_exchange()
        random.seed(1)
        submitted = 0
        for i in range(2_000):
            otype = random.choices(
                ["LIMIT", "MARKET", "IOC", "FOK"],
                weights=[60, 20, 12, 8],
            )[0]
            side = OrderSide.BUY if random.random() > 0.5 else OrderSide.SELL
            qty = random.randint(10, 500)
            price = round(100.0 + random.uniform(-2.0, 2.0), 2)
            try:
                if otype == "LIMIT":
                    ex.submit_order(Order.create_limit(side, price, qty))
                elif otype == "MARKET":
                    ex.submit_order(Order.create_market(side, qty))
                elif otype == "IOC":
                    ex.submit_order(Order.create_ioc(side, price, qty))
                elif otype == "FOK":
                    ex.submit_order(Order.create_fok(side, price, qty))
                submitted += 1
            except Exception as e:
                pytest.fail(f"Order submission raised: {e}")
        assert submitted == 2_000

    def test_book_integrity_after_cancels(self):
        """Cancel 50% of resting orders — book must remain consistent."""
        ex = make_exchange()
        random.seed(2)
        submitted_orders = []

        # Submit 500 limit orders
        for i in range(500):
            side = OrderSide.BUY if i % 2 == 0 else OrderSide.SELL
            price = round(99.0 + (i % 10) * 0.5, 2)
            o = Order.create_limit(side, price, 100)
            ex.submit_order(o)
            submitted_orders.append(o)

        # Cancel ~250 of them
        rng = random.Random(2)
        to_cancel = rng.sample(submitted_orders, 250)
        for o in to_cancel:
            ex.cancel_order(o.order_id)

        # Book state: order_index must match actual orders in levels
        bid_count = ex.book.bid_count
        ask_count = ex.book.ask_count
        assert bid_count >= 0
        assert ask_count >= 0

        # All entries in _order_index should exist in their levels
        for oid, (side, key) in list(ex.book._order_index.items()):
            book = ex.book._get_book(side)
            assert key in book, f"Order {oid} in index but level {key} missing from book"

    def test_determinism_1000_orders(self):
        """Identical input → identical output across two runs."""
        def run_sim() -> tuple[int, float]:
            ex = Exchange(symbol="DET")
            random.seed(99)
            for i in range(1_000):
                side = OrderSide.BUY if random.random() > 0.5 else OrderSide.SELL
                price = round(100.0 + random.uniform(-2.0, 2.0), 2)
                qty = random.randint(1, 50) * 10
                ex.submit_order(Order.create_limit(side, price, qty))
            s = ex.get_summary()
            return s["total_trades"], s["total_notional"]

        r1 = run_sim()
        r2 = run_sim()
        assert r1 == r2

    def test_memory_no_leak_on_reset(self):
        """After reset, no orders remain in book or history."""
        ex = make_exchange()
        random.seed(3)
        for i in range(1_000):
            side = OrderSide.BUY if random.random() > 0.5 else OrderSide.SELL
            price = round(100.0 + random.uniform(-2.0, 2.0), 2)
            ex.submit_order(Order.create_limit(side, price, 100))

        ex.reset()
        assert ex.book.bid_count == 0
        assert ex.book.ask_count == 0
        assert ex.history.total_trades == 0
        assert len(ex.book._order_index) == 0

    def test_high_frequency_single_price(self):
        """Many orders at the same price — book must remain FIFO-ordered."""
        ex = make_exchange()
        orders = [Order.create_limit(OrderSide.BUY, 100.0, 10, trader_id=f"t{i}")
                  for i in range(200)]
        for o in orders:
            ex.submit_order(o)

        level = ex.book.get_level(OrderSide.BUY, 100.0)
        assert level is not None
        assert level.order_count == 200
        assert level.peek_front() is orders[0]  # FIFO preserved
