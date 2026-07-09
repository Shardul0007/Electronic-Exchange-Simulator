"""
Unit tests for OrderValidator, CancelRequestValidator, and ModifyRequestValidator.
"""

import pytest

from exchange.orders.enums import OrderSide, OrderStatus, OrderType
from exchange.orders.models import Order
from exchange.orders.validator import (
    CancelRequestValidator,
    ModifyRequestValidator,
    OrderValidator,
    ValidationError,
)


def make_limit(
    side: OrderSide = OrderSide.BUY,
    price: float = 100.0,
    qty: int = 100,
    symbol: str = "AAPL",
) -> Order:
    return Order.create_limit(side=side, price=price, quantity=qty, symbol=symbol)


def make_market(side: OrderSide = OrderSide.BUY, qty: int = 100) -> Order:
    return Order.create_market(side=side, quantity=qty)


class TestOrderValidator:
    def test_valid_limit_order_passes(self):
        OrderValidator.validate(make_limit())  # No exception

    def test_valid_market_order_passes(self):
        OrderValidator.validate(make_market())

    # --- Price validation ---

    def test_market_order_with_price_fails(self):
        o = make_market()
        o.price = 100.0  # Inject price into market order
        with pytest.raises(ValidationError, match="must not specify a price"):
            OrderValidator.validate(o)

    def test_limit_order_without_price_fails(self):
        o = make_limit()
        o.price = None  # type: ignore
        with pytest.raises(ValidationError, match="require a price"):
            OrderValidator.validate(o)

    def test_negative_price_fails(self):
        o = make_limit(price=-10.0)
        with pytest.raises(ValidationError, match="positive"):
            OrderValidator.validate(o)

    def test_zero_price_fails(self):
        o = make_limit(price=0.0)
        with pytest.raises(ValidationError, match="positive"):
            OrderValidator.validate(o)

    def test_price_above_max_fails(self):
        o = make_limit(price=OrderValidator.MAX_PRICE + 1)
        with pytest.raises(ValidationError, match="exceeds maximum"):
            OrderValidator.validate(o)

    def test_invalid_tick_size_fails(self):
        o = make_limit(price=100.001)  # Not a multiple of 0.01
        with pytest.raises(ValidationError, match="tick"):
            OrderValidator.validate(o)

    def test_valid_tick_size_passes(self):
        o = make_limit(price=100.25)
        OrderValidator.validate(o)  # Should not raise

    # --- Quantity validation ---

    def test_zero_quantity_fails(self):
        o = make_limit(qty=0)
        with pytest.raises(ValidationError, match="positive"):
            OrderValidator.validate(o)

    def test_negative_quantity_fails(self):
        o = make_limit(qty=-1)
        with pytest.raises(ValidationError, match="positive"):
            OrderValidator.validate(o)

    def test_quantity_above_max_fails(self):
        o = make_limit(qty=OrderValidator.MAX_QUANTITY + 1)
        with pytest.raises(ValidationError, match="exceeds maximum"):
            OrderValidator.validate(o)

    # --- Symbol validation ---

    def test_empty_symbol_fails(self):
        o = make_limit(symbol="")
        with pytest.raises(ValidationError, match="empty"):
            OrderValidator.validate(o)

    def test_whitespace_symbol_fails(self):
        o = make_limit(symbol="   ")
        with pytest.raises(ValidationError, match="empty"):
            OrderValidator.validate(o)

    def test_long_symbol_fails(self):
        o = make_limit(symbol="TOOLONGSYMBOL")
        with pytest.raises(ValidationError, match="10 characters"):
            OrderValidator.validate(o)

    # --- Status validation ---

    def test_already_filled_order_fails(self):
        o = make_limit(qty=10)
        o.fill(10)
        with pytest.raises(ValidationError, match="status"):
            OrderValidator.validate(o)

    def test_cancelled_order_fails(self):
        o = make_limit()
        o.cancel()
        with pytest.raises(ValidationError, match="status"):
            OrderValidator.validate(o)


class TestCancelRequestValidator:
    def test_cancel_active_order_passes(self):
        o = make_limit()
        CancelRequestValidator.validate(o)  # No exception

    def test_cancel_partially_filled_passes(self):
        o = make_limit(qty=100)
        o.fill(50)
        CancelRequestValidator.validate(o)  # Still active

    def test_cancel_filled_order_fails(self):
        o = make_limit(qty=10)
        o.fill(10)
        with pytest.raises(ValidationError, match="cannot be cancelled"):
            CancelRequestValidator.validate(o)

    def test_cancel_already_cancelled_fails(self):
        o = make_limit()
        o.cancel()
        with pytest.raises(ValidationError, match="cannot be cancelled"):
            CancelRequestValidator.validate(o)


class TestModifyRequestValidator:
    def test_valid_modification_passes(self):
        o = make_limit(qty=100)
        ModifyRequestValidator.validate(o, new_qty=80, new_price=None)

    def test_modify_with_new_price(self):
        o = make_limit(qty=100)
        ModifyRequestValidator.validate(o, new_qty=100, new_price=105.0)

    def test_modify_zero_qty_fails(self):
        o = make_limit()
        with pytest.raises(ValidationError, match="positive"):
            ModifyRequestValidator.validate(o, new_qty=0, new_price=None)

    def test_modify_negative_qty_fails(self):
        o = make_limit()
        with pytest.raises(ValidationError, match="positive"):
            ModifyRequestValidator.validate(o, new_qty=-5, new_price=None)

    def test_modify_qty_below_filled_fails(self):
        o = make_limit(qty=100)
        o.fill(60)
        with pytest.raises(ValidationError, match="already filled"):
            ModifyRequestValidator.validate(o, new_qty=30, new_price=None)

    def test_modify_negative_price_fails(self):
        o = make_limit()
        with pytest.raises(ValidationError, match="positive"):
            ModifyRequestValidator.validate(o, new_qty=100, new_price=-5.0)

    def test_modify_price_on_market_order_fails(self):
        o = make_market()
        with pytest.raises(ValidationError, match="MARKET"):
            ModifyRequestValidator.validate(o, new_qty=100, new_price=100.0)

    def test_modify_cancelled_order_fails(self):
        o = make_limit()
        o.cancel()
        with pytest.raises(ValidationError, match="cannot be modified"):
            ModifyRequestValidator.validate(o, new_qty=50, new_price=None)

    def test_modify_filled_order_fails(self):
        o = make_limit(qty=10)
        o.fill(10)
        with pytest.raises(ValidationError, match="cannot be modified"):
            ModifyRequestValidator.validate(o, new_qty=5, new_price=None)
