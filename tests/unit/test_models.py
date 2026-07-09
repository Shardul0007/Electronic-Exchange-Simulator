"""
Unit tests for order domain models (Order, Trade, ExecutionReport).
"""

import pytest
from datetime import timezone

from exchange.orders.enums import (
    ExecType, OrderSide, OrderStatus, OrderType, TimeInForce
)
from exchange.orders.models import ExecutionReport, Order, Trade


class TestOrderCreation:
    def test_create_limit_buy(self):
        o = Order.create_limit(side=OrderSide.BUY, price=100.0, quantity=50)
        assert o.side == OrderSide.BUY
        assert o.price == 100.0
        assert o.quantity == 50
        assert o.remaining_qty == 50
        assert o.order_type == OrderType.LIMIT
        assert o.status == OrderStatus.NEW
        assert o.is_active is True

    def test_create_limit_sell(self):
        o = Order.create_limit(side=OrderSide.SELL, price=200.0, quantity=10)
        assert o.side == OrderSide.SELL
        assert o.price == 200.0

    def test_create_market_order(self):
        o = Order.create_market(side=OrderSide.BUY, quantity=100)
        assert o.order_type == OrderType.MARKET
        assert o.price is None
        assert o.time_in_force == TimeInForce.IOC

    def test_create_ioc_order(self):
        o = Order.create_ioc(side=OrderSide.BUY, price=50.0, quantity=20)
        assert o.order_type == OrderType.IOC
        assert o.time_in_force == TimeInForce.IOC

    def test_create_fok_order(self):
        o = Order.create_fok(side=OrderSide.SELL, price=75.0, quantity=30)
        assert o.order_type == OrderType.FOK
        assert o.time_in_force == TimeInForce.FOK

    def test_order_id_is_unique(self):
        ids = {Order.create_limit(OrderSide.BUY, 100.0, 10).order_id for _ in range(1000)}
        assert len(ids) == 1000

    def test_order_created_at_is_utc(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 10)
        assert o.created_at.tzinfo == timezone.utc

    def test_filled_qty_starts_at_zero(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 50)
        assert o.filled_qty == 0


class TestOrderFill:
    def test_partial_fill(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 100)
        o.fill(40)
        assert o.remaining_qty == 60
        assert o.filled_qty == 40
        assert o.status == OrderStatus.PARTIALLY_FILLED
        assert o.is_active is True

    def test_full_fill(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 100)
        o.fill(100)
        assert o.remaining_qty == 0
        assert o.filled_qty == 100
        assert o.status == OrderStatus.FILLED
        assert o.is_active is False

    def test_multiple_fills(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 100)
        o.fill(30)
        o.fill(30)
        o.fill(40)
        assert o.remaining_qty == 0
        assert o.filled_qty == 100
        assert o.status == OrderStatus.FILLED

    def test_fill_zero_raises(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 100)
        with pytest.raises(ValueError):
            o.fill(0)

    def test_fill_negative_raises(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 100)
        with pytest.raises(ValueError):
            o.fill(-10)

    def test_overfill_raises(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 50)
        with pytest.raises(ValueError):
            o.fill(100)


class TestOrderCancel:
    def test_cancel_active_order(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 50)
        o.cancel()
        assert o.status == OrderStatus.CANCELLED
        assert o.is_active is False

    def test_cancel_partially_filled_order(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 100)
        o.fill(50)
        o.cancel()
        assert o.status == OrderStatus.CANCELLED
        assert o.filled_qty == 50


class TestOrderModify:
    def test_modify_quantity(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 100)
        o.modify(new_qty=50)
        assert o.remaining_qty == 50
        assert o.status == OrderStatus.MODIFIED

    def test_modify_price(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 100)
        o.modify(new_qty=100, new_price=105.0)
        assert o.price == 105.0

    def test_modify_invalid_qty_raises(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 100)
        with pytest.raises(ValueError):
            o.modify(new_qty=0)


class TestOrderSerialization:
    def test_to_dict_has_required_keys(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 50)
        d = o.to_dict()
        required = {
            "order_id", "symbol", "side", "order_type", "price",
            "quantity", "remaining_qty", "filled_qty", "status",
            "created_at", "updated_at",
        }
        assert required.issubset(d.keys())

    def test_to_dict_enums_are_strings(self):
        o = Order.create_limit(OrderSide.BUY, 100.0, 50)
        d = o.to_dict()
        assert isinstance(d["side"], str)
        assert isinstance(d["order_type"], str)


class TestTrade:
    def test_create_trade(self):
        t = Trade.create(
            symbol="AAPL",
            price=150.0,
            quantity=100,
            buy_order_id="b1",
            sell_order_id="s1",
        )
        assert t.price == 150.0
        assert t.quantity == 100
        assert t.notional == 15000.0

    def test_trade_is_frozen(self):
        t = Trade.create(symbol="AAPL", price=100.0, quantity=10,
                         buy_order_id="b", sell_order_id="s")
        with pytest.raises(Exception):  # FrozenInstanceError
            t.price = 999.0  # type: ignore

    def test_trade_to_dict(self):
        t = Trade.create(symbol="AAPL", price=100.0, quantity=10,
                         buy_order_id="b", sell_order_id="s")
        d = t.to_dict()
        assert d["price"] == 100.0
        assert d["quantity"] == 10
        assert d["notional"] == 1000.0


class TestExecutionReport:
    def _make_order(self) -> Order:
        return Order.create_limit(OrderSide.BUY, 100.0, 100)

    def test_new_order_report(self):
        o = self._make_order()
        r = ExecutionReport.new_order(o)
        assert r.exec_type == ExecType.NEW
        assert r.filled_qty == 0
        assert r.remaining_qty == 100

    def test_cancel_report(self):
        o = self._make_order()
        r = ExecutionReport.cancel_report(o, reason="User cancelled")
        assert r.exec_type == ExecType.CANCELLED
        assert r.reject_reason == "User cancelled"

    def test_reject_report(self):
        o = self._make_order()
        r = ExecutionReport.reject_report(o, reason="Invalid price")
        assert r.exec_type == ExecType.REJECTED
        assert r.order_status == OrderStatus.REJECTED

    def test_exec_report_is_frozen(self):
        o = self._make_order()
        r = ExecutionReport.new_order(o)
        with pytest.raises(Exception):
            r.exec_type = ExecType.FILL  # type: ignore

    def test_to_dict_serialization(self):
        o = self._make_order()
        r = ExecutionReport.new_order(o)
        d = r.to_dict()
        assert d["exec_type"] == "NEW"
        assert d["order_status"] == "NEW"
