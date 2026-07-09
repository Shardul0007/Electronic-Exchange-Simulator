"""
Order input validation.

All validation logic lives here, keeping the Exchange and MatchingEngine
free from validation concerns (Single Responsibility).

Raises `ValidationError` — a domain-specific exception — rather than
generic ValueError so callers can distinguish validation failures from
programming errors.
"""

from __future__ import annotations

from exchange.orders.enums import OrderSide, OrderStatus, OrderType
from exchange.orders.models import Order


class ValidationError(Exception):
    """Raised when an order fails input validation."""

    def __init__(self, reason: str, order_id: str = "") -> None:
        self.reason = reason
        self.order_id = order_id
        super().__init__(f"ValidationError[{order_id}]: {reason}")


class OrderValidator:
    """
    Stateless order validator.

    All methods are class/static methods — no instance state needed.
    Inject this class wherever validation is needed (Dependency Injection).
    """

    # Maximum allowed price ($1,000,000 per unit — sanity cap)
    MAX_PRICE: float = 1_000_000.0

    # Maximum allowed quantity (100 million shares — sanity cap)
    MAX_QUANTITY: int = 100_000_000

    # Minimum tick size (prices must be multiples of this)
    TICK_SIZE: float = 0.01

    @classmethod
    def validate(cls, order: Order) -> None:
        """
        Validate an order before submission.

        Raises ValidationError on the first failing constraint.
        """
        cls._validate_symbol(order)
        cls._validate_quantity(order)
        cls._validate_price(order)
        cls._validate_status(order)
        cls._validate_order_type_consistency(order)

    @classmethod
    def _validate_symbol(cls, order: Order) -> None:
        if not order.symbol or not order.symbol.strip():
            raise ValidationError("Symbol cannot be empty", order.order_id)
        if len(order.symbol) > 10:
            raise ValidationError(
                f"Symbol '{order.symbol}' exceeds 10 characters", order.order_id
            )

    @classmethod
    def _validate_quantity(cls, order: Order) -> None:
        if order.quantity <= 0:
            raise ValidationError(
                f"Quantity must be positive, got {order.quantity}", order.order_id
            )
        if order.quantity > cls.MAX_QUANTITY:
            raise ValidationError(
                f"Quantity {order.quantity} exceeds maximum {cls.MAX_QUANTITY}",
                order.order_id,
            )
        if order.remaining_qty < 0:
            raise ValidationError(
                f"remaining_qty cannot be negative: {order.remaining_qty}",
                order.order_id,
            )

    @classmethod
    def _validate_price(cls, order: Order) -> None:
        if order.order_type == OrderType.MARKET:
            # Market orders must have no price
            if order.price is not None:
                raise ValidationError(
                    "Market orders must not specify a price", order.order_id
                )
            return

        # All non-market orders require a price
        if order.price is None:
            raise ValidationError(
                f"{order.order_type.value} orders require a price", order.order_id
            )

        if order.price <= 0:
            raise ValidationError(
                f"Price must be positive, got {order.price}", order.order_id
            )

        if order.price > cls.MAX_PRICE:
            raise ValidationError(
                f"Price {order.price} exceeds maximum {cls.MAX_PRICE}", order.order_id
            )

        # Tick size check (rounded to avoid floating point noise)
        rounded = round(order.price / cls.TICK_SIZE) * cls.TICK_SIZE
        if abs(rounded - order.price) > 1e-9:
            raise ValidationError(
                f"Price {order.price} is not a valid tick (tick size = {cls.TICK_SIZE})",
                order.order_id,
            )

    @classmethod
    def _validate_status(cls, order: Order) -> None:
        if order.status not in (OrderStatus.NEW, OrderStatus.MODIFIED):
            raise ValidationError(
                f"Cannot submit order with status {order.status.value} — "
                "only NEW or MODIFIED orders are accepted",
                order.order_id,
            )

    @classmethod
    def _validate_order_type_consistency(cls, order: Order) -> None:
        if order.side not in (OrderSide.BUY, OrderSide.SELL):
            raise ValidationError(
                f"Unknown order side: {order.side}", order.order_id
            )
        if order.order_type not in OrderType:
            raise ValidationError(
                f"Unknown order type: {order.order_type}", order.order_id
            )


class CancelRequestValidator:
    """Validates cancellation requests against the live order."""

    @staticmethod
    def validate(order: Order) -> None:
        """Raise ValidationError if the order cannot be cancelled."""
        if not order.is_active:
            raise ValidationError(
                f"Order {order.order_id} cannot be cancelled "
                f"(status={order.status.value})",
                order.order_id,
            )


class ModifyRequestValidator:
    """Validates modification requests against the live order."""

    @staticmethod
    def validate(order: Order, new_qty: int, new_price: float | None) -> None:
        """Raise ValidationError if the modification is invalid."""
        if not order.is_active:
            raise ValidationError(
                f"Order {order.order_id} cannot be modified "
                f"(status={order.status.value})",
                order.order_id,
            )
        if new_qty <= 0:
            raise ValidationError(
                f"new_qty must be positive, got {new_qty}", order.order_id
            )
        if new_qty < order.filled_qty:
            raise ValidationError(
                f"new_qty {new_qty} is less than already filled qty {order.filled_qty}",
                order.order_id,
            )
        if new_price is not None:
            if new_price <= 0:
                raise ValidationError(
                    f"new_price must be positive, got {new_price}", order.order_id
                )
            if order.order_type == OrderType.MARKET:
                raise ValidationError(
                    "Cannot modify price of a MARKET order", order.order_id
                )
