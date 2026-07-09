"""
Order domain enumerations.

All enums are `str` mixins so they serialise cleanly to JSON/CSV
without custom encoders (e.g. OrderType.LIMIT → "LIMIT").
"""

from __future__ import annotations

from enum import Enum


class OrderType(str, Enum):
    """The execution type of an order."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    IOC = "IOC"      # Immediate-or-Cancel
    FOK = "FOK"      # Fill-or-Kill
    GTC = "GTC"      # Good-Till-Cancel (same as LIMIT in this engine; kept for clarity)


class OrderSide(str, Enum):
    """Which side of the book an order lives on."""

    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> "OrderSide":
        return OrderSide.SELL if self == OrderSide.BUY else OrderSide.BUY


class OrderStatus(str, Enum):
    """Lifecycle state of a single order."""

    NEW = "NEW"                      # Accepted, not yet matched
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    PENDING_CANCEL = "PENDING_CANCEL"
    PENDING_MODIFY = "PENDING_MODIFY"
    MODIFIED = "MODIFIED"


class ExecType(str, Enum):
    """
    The type of an ExecutionReport.

    Mirrors FIX Protocol tag 150 (ExecType).
    """

    NEW = "NEW"                      # Order accepted
    PARTIAL_FILL = "PARTIAL_FILL"    # Partial fill occurred
    FILL = "FILL"                    # Order fully filled
    CANCELLED = "CANCELLED"          # Order cancelled
    REJECTED = "REJECTED"            # Order rejected (validation failure)
    MODIFIED = "MODIFIED"            # Order modified (qty/price change)
    TRADE = "TRADE"                  # A trade occurred (informational)


class TimeInForce(str, Enum):
    """
    How long an order stays active.

    In this engine, TimeInForce overlaps with OrderType for IOC/FOK/GTC,
    but is kept separate to mirror real FIX Protocol designs.
    """

    DAY = "DAY"          # Cancel at end of session (treated as GTC in simulation)
    GTC = "GTC"          # Good Till Cancel
    IOC = "IOC"          # Immediate or Cancel
    FOK = "FOK"          # Fill or Kill


class ReplaySpeed(str, Enum):
    """Speed modes for the replay engine."""

    INSTANT = "INSTANT"           # Replay as fast as possible
    ACCELERATED = "ACCELERATED"   # Replay at N× real-time speed
    REAL_TIME = "REAL_TIME"       # Honour original timestamps (1×)
