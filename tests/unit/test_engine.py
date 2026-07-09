"""
Unit tests for the MatchingEngine.

Tests cover:
  - Limit order matching (full and partial fills)
  - Market order execution
  - IOC order (fill + cancel remainder)
  - FOK order (full fill or cancel)
  - Price-time priority (FIFO at price levels)
  - Order cancellation
  - Order modification
  - Self-trade prevention
  - Multiple fills in a single submission
  - VWAP calculation
"""

import pytest

from exchange.matching.engine import MatchingEngine
from exchange.matching.order_book import LimitOrderBook
from exchange.orders.enums import ExecType, OrderSide, OrderStatus, OrderType
from exchange.orders.models import Order


def make_engine() -> MatchingEngine:
    book = LimitOrderBook(symbol="AAPL")
    return MatchingEngine(book)


def limit(side: OrderSide, price: float, qty: int, trader: str = "trader1") -> Order:
    return Order.create_limit(side=side, price=price, quantity=qty, trader_id=trader)


def market(side: OrderSide, qty: int, trader: str = "trader1") -> Order:
    return Order.create_market(side=side, quantity=qty, trader_id=trader)


def ioc(side: OrderSide, price: float, qty: int) -> Order:
    return Order.create_ioc(side=side, price=price, quantity=qty)


def fok(side: OrderSide, price: float, qty: int) -> Order:
    return Order.create_fok(side=side, price=price, quantity=qty)


class TestLimitOrderMatching:
    def test_no_match_limit_rests_in_book(self):
        eng = make_engine()
        buy = limit(OrderSide.BUY, 100.0, 50)
        reports = eng.submit_order(buy)
        assert any(r.exec_type == ExecType.NEW for r in reports)
        assert eng.book.bid_count == 1
        assert eng.trade_count == 0

    def test_limit_crosses_limit_full_fill(self):
        eng = make_engine()
        sell = limit(OrderSide.SELL, 100.0, 50, trader="seller")
        eng.submit_order(sell)

        buy = limit(OrderSide.BUY, 100.0, 50, trader="buyer")
        reports = eng.submit_order(buy)

        trades = eng.get_trades()
        assert len(trades) == 1
        assert trades[0].price == 100.0
        assert trades[0].quantity == 50
        assert eng.book.bid_count == 0
        assert eng.book.ask_count == 0

        # Both sides get FILL reports
        fill_reports = [r for r in reports if r.exec_type == ExecType.FILL]
        assert len(fill_reports) == 2

    def test_limit_crosses_with_partial_fill(self):
        eng = make_engine()
        sell = limit(OrderSide.SELL, 100.0, 30, trader="seller")
        eng.submit_order(sell)

        buy = limit(OrderSide.BUY, 100.0, 100, trader="buyer")
        reports = eng.submit_order(buy)

        trades = eng.get_trades()
        assert len(trades) == 1
        assert trades[0].quantity == 30

        # Buy order partially filled, 70 remain
        assert eng.book.bid_count == 1
        assert eng.book.total_bid_qty() == 70

    def test_buy_limit_fills_multiple_ask_levels(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 20, "s1"))
        eng.submit_order(limit(OrderSide.SELL, 101.0, 30, "s2"))
        eng.submit_order(limit(OrderSide.SELL, 102.0, 50, "s3"))

        buy = limit(OrderSide.BUY, 103.0, 100, "buyer")
        eng.submit_order(buy)

        trades = eng.get_trades()
        assert len(trades) == 3
        assert sum(t.quantity for t in trades) == 100
        assert eng.book.ask_count == 0

    def test_price_priority_lower_ask_fills_first(self):
        eng = make_engine()
        # Insert asks out of order
        eng.submit_order(limit(OrderSide.SELL, 102.0, 50, "s2"))
        eng.submit_order(limit(OrderSide.SELL, 100.0, 50, "s1"))
        eng.submit_order(limit(OrderSide.SELL, 101.0, 50, "s3"))

        buy = limit(OrderSide.BUY, 102.0, 50, "buyer")
        eng.submit_order(buy)

        trades = eng.get_trades()
        assert len(trades) == 1
        assert trades[0].price == 100.0  # Filled at best ask (lowest price)

    def test_time_priority_same_price_fifo(self):
        eng = make_engine()
        s1 = limit(OrderSide.SELL, 100.0, 30, "s1")
        s2 = limit(OrderSide.SELL, 100.0, 30, "s2")
        eng.submit_order(s1)
        eng.submit_order(s2)

        buy = limit(OrderSide.BUY, 100.0, 30, "buyer")
        eng.submit_order(buy)

        trades = eng.get_trades()
        # Must fill against s1 (arrived first)
        assert trades[0].sell_order_id == s1.order_id


class TestMarketOrders:
    def test_market_buy_fills_at_best_ask(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 50, "seller"))

        buy = market(OrderSide.BUY, 50)
        eng.submit_order(buy)

        trades = eng.get_trades()
        assert len(trades) == 1
        assert trades[0].price == 100.0

    def test_market_order_no_liquidity_cancels(self):
        eng = make_engine()
        buy = market(OrderSide.BUY, 100)
        reports = eng.submit_order(buy)

        cancel_reports = [r for r in reports if r.exec_type == ExecType.CANCELLED]
        assert len(cancel_reports) == 1
        assert eng.trade_count == 0

    def test_market_order_partial_fill_then_cancel(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 30, "seller"))

        buy = market(OrderSide.BUY, 100)
        reports = eng.submit_order(buy)

        trades = eng.get_trades()
        assert trades[0].quantity == 30

        cancel_reports = [r for r in reports if r.exec_type == ExecType.CANCELLED]
        assert len(cancel_reports) == 1

    def test_market_order_does_not_rest_in_book(self):
        eng = make_engine()
        buy = market(OrderSide.BUY, 100)
        eng.submit_order(buy)
        assert eng.book.bid_count == 0


class TestIOCOrders:
    def test_ioc_partial_fill_cancels_residual(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 30, "seller"))

        order = ioc(OrderSide.BUY, 100.0, 100)
        reports = eng.submit_order(order)

        trades = eng.get_trades()
        assert trades[0].quantity == 30

        cancel_reports = [r for r in reports if r.exec_type == ExecType.CANCELLED]
        assert len(cancel_reports) == 1
        assert eng.book.bid_count == 0  # IOC never rests

    def test_ioc_no_fill_cancels(self):
        eng = make_engine()
        order = ioc(OrderSide.BUY, 100.0, 50)
        reports = eng.submit_order(order)
        assert any(r.exec_type == ExecType.CANCELLED for r in reports)

    def test_ioc_full_fill_no_cancel(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 50, "seller"))
        order = ioc(OrderSide.BUY, 100.0, 50)
        reports = eng.submit_order(order)
        assert any(r.exec_type == ExecType.FILL for r in reports)
        cancel_reports = [r for r in reports if r.exec_type == ExecType.CANCELLED]
        assert len(cancel_reports) == 0


class TestFOKOrders:
    def test_fok_full_liquidity_executes(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 100, "seller"))
        order = fok(OrderSide.BUY, 100.0, 100)
        reports = eng.submit_order(order)
        assert any(r.exec_type == ExecType.FILL for r in reports)
        assert eng.trade_count == 1

    def test_fok_partial_liquidity_cancels(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 30, "seller"))
        order = fok(OrderSide.BUY, 100.0, 100)
        reports = eng.submit_order(order)
        assert all(r.exec_type == ExecType.CANCELLED for r in reports)
        assert eng.trade_count == 0

    def test_fok_no_liquidity_cancels(self):
        eng = make_engine()
        order = fok(OrderSide.BUY, 100.0, 50)
        reports = eng.submit_order(order)
        assert any(r.exec_type == ExecType.CANCELLED for r in reports)

    def test_fok_wrong_price_cancels(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 105.0, 100, "seller"))
        order = fok(OrderSide.BUY, 100.0, 100)  # Won't cross at 105
        reports = eng.submit_order(order)
        assert any(r.exec_type == ExecType.CANCELLED for r in reports)
        assert eng.trade_count == 0


class TestCancellation:
    def test_cancel_resting_order(self):
        eng = make_engine()
        buy = limit(OrderSide.BUY, 100.0, 50)
        eng.submit_order(buy)
        report = eng.cancel_order(buy.order_id)
        assert report is not None
        assert report.exec_type == ExecType.CANCELLED
        assert eng.book.bid_count == 0

    def test_cancel_nonexistent_returns_none(self):
        eng = make_engine()
        result = eng.cancel_order("nonexistent")
        assert result is None

    def test_cancel_already_matched_order_fails(self):
        eng = make_engine()
        sell = limit(OrderSide.SELL, 100.0, 50, "seller")
        buy = limit(OrderSide.BUY, 100.0, 50, "buyer")
        eng.submit_order(sell)
        eng.submit_order(buy)
        # Both fully filled — cancel should fail
        result = eng.cancel_order(sell.order_id)
        assert result is None


class TestModification:
    def test_modify_quantity_in_place(self):
        eng = make_engine()
        buy = limit(OrderSide.BUY, 100.0, 100)
        eng.submit_order(buy)
        report = eng.modify_order(buy.order_id, new_quantity=50)
        assert report is not None
        assert report.exec_type == ExecType.MODIFIED
        assert eng.book.total_bid_qty() == 50

    def test_modify_price_requeues(self):
        eng = make_engine()
        buy = limit(OrderSide.BUY, 100.0, 100)
        eng.submit_order(buy)
        report = eng.modify_order(buy.order_id, new_quantity=100, new_price=101.0)
        assert report is not None
        assert eng.book.best_bid() == 101.0


class TestSelfTradePrevention:
    def test_stp_skips_self_trade(self):
        eng = make_engine()
        sell = limit(OrderSide.SELL, 100.0, 50, trader="same_trader")
        buy = limit(OrderSide.BUY, 100.0, 50, trader="same_trader")
        eng.submit_order(sell)
        eng.submit_order(buy)
        # Self-trade prevented: no trades generated
        assert eng.trade_count == 0

    def test_no_stp_different_traders(self):
        eng = make_engine()
        sell = limit(OrderSide.SELL, 100.0, 50, trader="trader_a")
        buy = limit(OrderSide.BUY, 100.0, 50, trader="trader_b")
        eng.submit_order(sell)
        eng.submit_order(buy)
        assert eng.trade_count == 1


class TestAverageFillPrice:
    def test_vwap_single_trade(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 100, "seller"))
        eng.submit_order(limit(OrderSide.BUY, 100.0, 100, "buyer"))
        assert eng.vwap() == pytest.approx(100.0)

    def test_vwap_multiple_fills(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 50, "s1"))
        eng.submit_order(limit(OrderSide.SELL, 102.0, 50, "s2"))
        eng.submit_order(limit(OrderSide.BUY, 103.0, 100, "buyer"))
        # VWAP = (100*50 + 102*50) / 100 = 101.0
        assert eng.vwap() == pytest.approx(101.0)

    def test_vwap_empty_no_trades(self):
        eng = make_engine()
        assert eng.vwap() is None


class TestEngineReset:
    def test_reset_clears_trades(self):
        eng = make_engine()
        eng.submit_order(limit(OrderSide.SELL, 100.0, 50, "s"))
        eng.submit_order(limit(OrderSide.BUY, 100.0, 50, "b"))
        assert eng.trade_count > 0
        eng.reset()
        assert eng.trade_count == 0
        assert eng.vwap() is None
