"""
Integration tests for the Exchange facade.

Tests the full order lifecycle end-to-end:
  submit → validate → match → record → publish
"""

import pytest

from exchange.core.exchange import Exchange
from exchange.orders.enums import ExecType, OrderSide, OrderStatus
from exchange.orders.models import Order
from exchange.orders.validator import ValidationError


def make_exchange() -> Exchange:
    return Exchange(symbol="AAPL")


def limit(side: OrderSide, price: float, qty: int, trader: str = "t1") -> Order:
    return Order.create_limit(side=side, price=price, quantity=qty, trader_id=trader)


def market(side: OrderSide, qty: int) -> Order:
    return Order.create_market(side=side, quantity=qty)


class TestExchangeSubmit:
    def test_submit_limit_order_returns_new_report(self):
        ex = make_exchange()
        buy = limit(OrderSide.BUY, 100.0, 50)
        reports = ex.submit_order(buy)
        assert any(r.exec_type == ExecType.NEW for r in reports)

    def test_submit_invalid_order_returns_reject_report(self):
        ex = make_exchange()
        bad = limit(OrderSide.BUY, -1.0, 50)  # Negative price
        reports = ex.submit_order(bad)
        assert len(reports) == 1
        assert reports[0].exec_type == ExecType.REJECTED

    def test_rejected_order_in_history(self):
        ex = make_exchange()
        bad = limit(OrderSide.BUY, 0.0, 50)
        ex.submit_order(bad)
        history = ex.get_execution_history()
        assert any(r.exec_type == ExecType.REJECTED for r in history)

    def test_full_fill_generates_trade(self):
        ex = make_exchange()
        ex.submit_order(limit(OrderSide.SELL, 100.0, 50, "seller"))
        ex.submit_order(limit(OrderSide.BUY, 100.0, 50, "buyer"))
        trades = ex.get_trades()
        assert len(trades) == 1
        assert trades[0].price == 100.0
        assert trades[0].quantity == 50

    def test_market_data_published_after_submit(self):
        ex = make_exchange()
        ex.submit_order(limit(OrderSide.BUY, 100.0, 50))
        data = ex.get_market_data()
        assert "bids" in data
        assert "asks" in data
        assert data["best_bid"] == 100.0

    def test_market_data_spread_after_both_sides(self):
        ex = make_exchange()
        ex.submit_order(limit(OrderSide.BUY, 100.0, 50))
        ex.submit_order(limit(OrderSide.SELL, 102.0, 50))
        data = ex.get_market_data()
        assert data["spread"] == pytest.approx(2.0)


class TestExchangeCancel:
    def test_cancel_resting_order(self):
        ex = make_exchange()
        buy = limit(OrderSide.BUY, 100.0, 50)
        ex.submit_order(buy)
        report = ex.cancel_order(buy.order_id)
        assert report is not None
        assert report.exec_type == ExecType.CANCELLED
        assert ex.book.bid_count == 0

    def test_cancel_nonexistent_returns_none(self):
        ex = make_exchange()
        result = ex.cancel_order("nonexistent")
        assert result is None

    def test_cancel_recorded_in_history(self):
        ex = make_exchange()
        buy = limit(OrderSide.BUY, 100.0, 50)
        ex.submit_order(buy)
        ex.cancel_order(buy.order_id)
        history = ex.get_execution_history()
        assert any(r.exec_type == ExecType.CANCELLED for r in history)


class TestExchangeModify:
    def test_modify_resting_order(self):
        ex = make_exchange()
        buy = limit(OrderSide.BUY, 100.0, 100)
        ex.submit_order(buy)
        report = ex.modify_order(buy.order_id, new_quantity=50)
        assert report is not None
        assert report.exec_type == ExecType.MODIFIED
        assert ex.book.total_bid_qty() == 50

    def test_modify_nonexistent_returns_none(self):
        ex = make_exchange()
        result = ex.modify_order("nonexistent", 50)
        assert result is None


class TestExchangeSummary:
    def test_summary_after_fills(self):
        ex = make_exchange()
        ex.submit_order(limit(OrderSide.SELL, 100.0, 50, "seller"))
        ex.submit_order(limit(OrderSide.BUY, 100.0, 50, "buyer"))
        summary = ex.get_summary()
        assert summary["total_trades"] == 1
        assert summary["total_volume"] == 50
        assert summary["total_notional"] == pytest.approx(5000.0)
        assert summary["vwap"] == pytest.approx(100.0)

    def test_fill_rate_full_fills(self):
        ex = make_exchange()
        ex.submit_order(limit(OrderSide.SELL, 100.0, 100, "seller"))
        ex.submit_order(limit(OrderSide.BUY, 100.0, 100, "buyer"))
        summary = ex.get_summary()
        # Both orders fully filled
        assert summary["fill_rate"] > 0

    def test_latency_stats_populated(self):
        ex = make_exchange()
        for _ in range(10):
            ex.submit_order(limit(OrderSide.BUY, 100.0, 10))
        stats = ex.get_latency_stats()
        assert stats["count"] == 10
        assert "p99_us" in stats
        assert stats["mean_us"] >= 0


class TestExchangeReset:
    def test_reset_clears_state(self):
        ex = make_exchange()
        ex.submit_order(limit(OrderSide.SELL, 100.0, 50, "s"))
        ex.submit_order(limit(OrderSide.BUY, 100.0, 50, "b"))
        ex.reset()
        assert ex.history.total_trades == 0
        assert ex.book.bid_count == 0
        assert ex.book.ask_count == 0


class TestExchangeStressLight:
    def test_100_random_orders(self):
        """Sanity check: 100 orders processed without error."""
        import random
        ex = make_exchange()
        for i in range(100):
            side = OrderSide.BUY if i % 2 == 0 else OrderSide.SELL
            price = round(100.0 + random.uniform(-2.0, 2.0), 2)
            qty = random.randint(1, 100)
            ex.submit_order(limit(side, price, qty, f"trader_{i % 10}"))
        # No exceptions = pass
        assert True
