"""
Core order domain models.

All models use Python dataclasses. Orders use regular (mutable) dataclasses
because their state changes over their lifecycle (fills reduce remaining_qty).
Trades and ExecutionReports are frozen — they are immutable facts.

Design note: `__slots__ = True` on frozen dataclasses reduces memory by ~20%
for large numbers of objects, which matters at simulation scale.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar

from exchange.orders.enums import ExecType, OrderSide, OrderStatus, OrderType, TimeInForce


def _now() -> datetime:
    """Return current UTC time (isolated for testability)."""
    return datetime.now(timezone.utc)


def _new_id() -> str:
    """Generate a new UUID4 order/trade identifier."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------

@dataclass
class Order:
    """
    Represents a single order submitted to the exchange.

    An Order is mutable: `remaining_qty` decreases as fills arrive,
    and `status` transitions through its lifecycle.

    Do NOT construct directly — use the factory class methods
    `Order.create_limit`, `Order.create_market`, etc.
    """

    # Immutable identity fields
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce

    # Price & quantity
    price: float | None          # None for MARKET orders
    quantity: int                # Original submitted quantity
    remaining_qty: int           # Decremented on each fill

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Mutable state
    status: OrderStatus

    # Optional metadata
    trader_id: str = "anonymous"
    client_order_id: str = ""

    # ---- Factory methods ---------------------------------------------------

    @classmethod
    def create_limit(
        cls,
        side: OrderSide,
        price: float,
        quantity: int,
        symbol: str = "AAPL",
        trader_id: str = "anonymous",
        time_in_force: TimeInForce = TimeInForce.GTC,
        client_order_id: str = "",
    ) -> "Order":
        """Create a Limit order."""
        now = _now()
        return cls(
            order_id=_new_id(),
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            time_in_force=time_in_force,
            price=price,
            quantity=quantity,
            remaining_qty=quantity,
            created_at=now,
            updated_at=now,
            status=OrderStatus.NEW,
            trader_id=trader_id,
            client_order_id=client_order_id,
        )

    @classmethod
    def create_market(
        cls,
        side: OrderSide,
        quantity: int,
        symbol: str = "AAPL",
        trader_id: str = "anonymous",
        client_order_id: str = "",
    ) -> "Order":
        """Create a Market order (no price)."""
        now = _now()
        return cls(
            order_id=_new_id(),
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IOC,  # Market orders are always IOC semantically
            price=None,
            quantity=quantity,
            remaining_qty=quantity,
            created_at=now,
            updated_at=now,
            status=OrderStatus.NEW,
            trader_id=trader_id,
            client_order_id=client_order_id,
        )

    @classmethod
    def create_ioc(
        cls,
        side: OrderSide,
        price: float,
        quantity: int,
        symbol: str = "AAPL",
        trader_id: str = "anonymous",
    ) -> "Order":
        """Create an IOC (Immediate-or-Cancel) limit order."""
        now = _now()
        return cls(
            order_id=_new_id(),
            symbol=symbol,
            side=side,
            order_type=OrderType.IOC,
            time_in_force=TimeInForce.IOC,
            price=price,
            quantity=quantity,
            remaining_qty=quantity,
            created_at=now,
            updated_at=now,
            status=OrderStatus.NEW,
            trader_id=trader_id,
        )

    @classmethod
    def create_fok(
        cls,
        side: OrderSide,
        price: float,
        quantity: int,
        symbol: str = "AAPL",
        trader_id: str = "anonymous",
    ) -> "Order":
        """Create a FOK (Fill-or-Kill) limit order."""
        now = _now()
        return cls(
            order_id=_new_id(),
            symbol=symbol,
            side=side,
            order_type=OrderType.FOK,
            time_in_force=TimeInForce.FOK,
            price=price,
            quantity=quantity,
            remaining_qty=quantity,
            created_at=now,
            updated_at=now,
            status=OrderStatus.NEW,
            trader_id=trader_id,
        )

    # ---- State helpers -----------------------------------------------------

    def fill(self, qty: int) -> None:
        """Apply a fill of `qty` units. Updates remaining_qty and status."""
        if qty <= 0 or qty > self.remaining_qty:
            raise ValueError(
                f"Invalid fill qty {qty} for order {self.order_id} "
                f"(remaining={self.remaining_qty})"
            )
        self.remaining_qty -= qty
        self.updated_at = _now()
        self.status = (
            OrderStatus.FILLED if self.remaining_qty == 0
            else OrderStatus.PARTIALLY_FILLED
        )

    def cancel(self) -> None:
        """Mark the order as cancelled."""
        self.status = OrderStatus.CANCELLED
        self.updated_at = _now()

    def modify(self, new_qty: int, new_price: float | None = None) -> None:
        """Modify quantity (and optionally price). Resets time-priority."""
        if new_qty <= 0:
            raise ValueError(f"new_qty must be positive, got {new_qty}")
        delta = self.remaining_qty - new_qty
        self.remaining_qty = new_qty
        self.quantity = self.quantity - delta
        if new_price is not None:
            self.price = new_price
        self.status = OrderStatus.MODIFIED
        self.updated_at = _now()

    @property
    def is_active(self) -> bool:
        """True if the order can still be matched or cancelled."""
        return self.status in (
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.MODIFIED,
        )

    @property
    def filled_qty(self) -> int:
        """How many units have already been filled."""
        return self.quantity - self.remaining_qty

    def to_dict(self) -> dict:
        """Serialise to a plain dict (JSON/CSV compatible)."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "time_in_force": self.time_in_force.value,
            "price": self.price,
            "quantity": self.quantity,
            "remaining_qty": self.remaining_qty,
            "filled_qty": self.filled_qty,
            "status": self.status.value,
            "trader_id": self.trader_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"Order(id={self.order_id[:8]}, {self.side.value} {self.remaining_qty}"
            f"@{self.price}, type={self.order_type.value}, status={self.status.value})"
        )


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Trade:
    """
    An immutable record of a matched trade.

    Trades are facts — once generated they must never be mutated.
    Frozen dataclass ensures hashability and prevents accidental modification.
    """

    trade_id: str
    symbol: str
    price: float
    quantity: int

    buy_order_id: str
    sell_order_id: str

    buyer_trader_id: str
    seller_trader_id: str

    executed_at: datetime

    @classmethod
    def create(
        cls,
        symbol: str,
        price: float,
        quantity: int,
        buy_order_id: str,
        sell_order_id: str,
        buyer_trader_id: str = "anonymous",
        seller_trader_id: str = "anonymous",
    ) -> "Trade":
        """Factory method for creating a Trade."""
        return cls(
            trade_id=_new_id(),
            symbol=symbol,
            price=price,
            quantity=quantity,
            buy_order_id=buy_order_id,
            sell_order_id=sell_order_id,
            buyer_trader_id=buyer_trader_id,
            seller_trader_id=seller_trader_id,
            executed_at=_now(),
        )

    @property
    def notional(self) -> float:
        """Total notional value of the trade (price × quantity)."""
        return self.price * self.quantity

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "price": self.price,
            "quantity": self.quantity,
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
            "buyer_trader_id": self.buyer_trader_id,
            "seller_trader_id": self.seller_trader_id,
            "executed_at": self.executed_at.isoformat(),
            "notional": self.notional,
        }

    def __repr__(self) -> str:
        return f"Trade(id={self.trade_id[:8]}, {self.quantity}@{self.price})"


# ---------------------------------------------------------------------------
# ExecutionReport
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """
    Execution report sent back to the order submitter.

    Mirrors the FIX Protocol ExecutionReport (MsgType=8).
    One report is generated for each significant order event:
    acceptance, fill, partial fill, cancellation, rejection, modification.
    """

    exec_id: str
    order_id: str
    symbol: str

    exec_type: ExecType
    order_status: OrderStatus
    order_side: OrderSide
    order_type: OrderType

    # Quantities
    order_qty: int
    filled_qty: int
    remaining_qty: int
    last_fill_qty: int       # Qty filled in THIS report (0 if non-fill event)
    last_fill_price: float   # Price of THIS fill (0.0 if non-fill event)

    # Averages
    avg_fill_price: float    # Cumulative average fill price

    # Timestamps
    timestamp: datetime

    # Optional
    trade_id: str = ""          # Associated trade ID (if fill)
    reject_reason: str = ""     # Human-readable rejection reason
    trader_id: str = "anonymous"

    @classmethod
    def new_order(cls, order: "Order") -> "ExecutionReport":
        """Report confirming a new order was accepted."""
        return cls(
            exec_id=_new_id(),
            order_id=order.order_id,
            symbol=order.symbol,
            exec_type=ExecType.NEW,
            order_status=OrderStatus.NEW,
            order_side=order.side,
            order_type=order.order_type,
            order_qty=order.quantity,
            filled_qty=0,
            remaining_qty=order.remaining_qty,
            last_fill_qty=0,
            last_fill_price=0.0,
            avg_fill_price=0.0,
            timestamp=_now(),
            trader_id=order.trader_id,
        )

    @classmethod
    def fill_report(
        cls,
        order: "Order",
        trade: "Trade",
        avg_fill_price: float,
    ) -> "ExecutionReport":
        """Report for a fill (full or partial)."""
        is_full = order.remaining_qty == 0
        return cls(
            exec_id=_new_id(),
            order_id=order.order_id,
            symbol=order.symbol,
            exec_type=ExecType.FILL if is_full else ExecType.PARTIAL_FILL,
            order_status=order.status,
            order_side=order.side,
            order_type=order.order_type,
            order_qty=order.quantity,
            filled_qty=order.filled_qty,
            remaining_qty=order.remaining_qty,
            last_fill_qty=trade.quantity,
            last_fill_price=trade.price,
            avg_fill_price=avg_fill_price,
            timestamp=trade.executed_at,
            trade_id=trade.trade_id,
            trader_id=order.trader_id,
        )

    @classmethod
    def cancel_report(cls, order: "Order", reason: str = "") -> "ExecutionReport":
        """Report confirming an order was cancelled."""
        return cls(
            exec_id=_new_id(),
            order_id=order.order_id,
            symbol=order.symbol,
            exec_type=ExecType.CANCELLED,
            order_status=OrderStatus.CANCELLED,
            order_side=order.side,
            order_type=order.order_type,
            order_qty=order.quantity,
            filled_qty=order.filled_qty,
            remaining_qty=order.remaining_qty,
            last_fill_qty=0,
            last_fill_price=0.0,
            avg_fill_price=0.0,
            timestamp=_now(),
            reject_reason=reason,
            trader_id=order.trader_id,
        )

    @classmethod
    def reject_report(cls, order: "Order", reason: str) -> "ExecutionReport":
        """Report confirming an order was rejected at validation."""
        return cls(
            exec_id=_new_id(),
            order_id=order.order_id,
            symbol=order.symbol,
            exec_type=ExecType.REJECTED,
            order_status=OrderStatus.REJECTED,
            order_side=order.side,
            order_type=order.order_type,
            order_qty=order.quantity,
            filled_qty=0,
            remaining_qty=order.remaining_qty,
            last_fill_qty=0,
            last_fill_price=0.0,
            avg_fill_price=0.0,
            timestamp=_now(),
            reject_reason=reason,
            trader_id=order.trader_id,
        )

    @classmethod
    def modify_report(cls, order: "Order") -> "ExecutionReport":
        """Report confirming an order was modified."""
        return cls(
            exec_id=_new_id(),
            order_id=order.order_id,
            symbol=order.symbol,
            exec_type=ExecType.MODIFIED,
            order_status=OrderStatus.MODIFIED,
            order_side=order.side,
            order_type=order.order_type,
            order_qty=order.quantity,
            filled_qty=order.filled_qty,
            remaining_qty=order.remaining_qty,
            last_fill_qty=0,
            last_fill_price=0.0,
            avg_fill_price=0.0,
            timestamp=_now(),
            trader_id=order.trader_id,
        )

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        return {
            "exec_id": self.exec_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "exec_type": self.exec_type.value,
            "order_status": self.order_status.value,
            "order_side": self.order_side.value,
            "order_type": self.order_type.value,
            "order_qty": self.order_qty,
            "filled_qty": self.filled_qty,
            "remaining_qty": self.remaining_qty,
            "last_fill_qty": self.last_fill_qty,
            "last_fill_price": self.last_fill_price,
            "avg_fill_price": self.avg_fill_price,
            "trade_id": self.trade_id,
            "reject_reason": self.reject_reason,
            "timestamp": self.timestamp.isoformat(),
            "trader_id": self.trader_id,
        }

    def __repr__(self) -> str:
        return (
            f"ExecutionReport(order={self.order_id[:8]}, "
            f"type={self.exec_type.value}, "
            f"fill={self.last_fill_qty}@{self.last_fill_price})"
        )
