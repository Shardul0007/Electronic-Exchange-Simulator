"""
CSV Order Loader for the Replay Engine.

Parses CSV files into Order objects. The CSV format is:

  order_id,symbol,side,order_type,price,quantity,trader_id,timestamp

Required columns: side, order_type, quantity
Optional columns: order_id, symbol, price, trader_id, timestamp

- order_id: auto-generated if missing
- symbol: defaults to "AAPL" if missing
- price: required for non-MARKET orders; blank/empty for MARKET
- timestamp: ISO 8601 or Unix timestamp (seconds float); optional for replay timing
"""

from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path

from exchange.orders.enums import OrderSide, OrderType, TimeInForce
from exchange.orders.models import Order


class CSVParseError(Exception):
    """Raised when the CSV file cannot be parsed into valid orders."""


class ReplayLoader:
    """
    Loads a CSV file and converts each row into an Order object.

    Designed for deterministic replay: the same CSV always produces
    the same sequence of orders.
    """

    REQUIRED_COLUMNS = {"side", "order_type", "quantity"}

    SIDE_MAP: dict[str, OrderSide] = {
        "BUY": OrderSide.BUY,
        "B": OrderSide.BUY,
        "SELL": OrderSide.SELL,
        "S": OrderSide.SELL,
    }

    TYPE_MAP: dict[str, OrderType] = {
        "LIMIT": OrderType.LIMIT,
        "L": OrderType.LIMIT,
        "MARKET": OrderType.MARKET,
        "MKT": OrderType.MARKET,
        "M": OrderType.MARKET,
        "IOC": OrderType.IOC,
        "FOK": OrderType.FOK,
        "GTC": OrderType.GTC,
    }

    TIF_MAP: dict[str, TimeInForce] = {
        "GTC": TimeInForce.GTC,
        "IOC": TimeInForce.IOC,
        "FOK": TimeInForce.FOK,
        "DAY": TimeInForce.DAY,
    }

    @classmethod
    def load(cls, path: str | Path) -> list[Order]:
        """
        Parse a CSV file and return a list of Orders.

        Raises CSVParseError for malformed rows (with line number).
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Replay file not found: {path}")

        orders: list[Order] = []
        errors: list[str] = []

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise CSVParseError("CSV file has no header row")

            headers = {h.strip().lower() for h in reader.fieldnames}
            missing = cls.REQUIRED_COLUMNS - headers
            if missing:
                raise CSVParseError(
                    f"CSV missing required columns: {missing}. "
                    f"Found: {headers}"
                )

            for line_num, row in enumerate(reader, start=2):
                try:
                    order = cls._parse_row(row)
                    orders.append(order)
                except (ValueError, KeyError) as exc:
                    errors.append(f"Line {line_num}: {exc}")

        if errors:
            raise CSVParseError(
                f"Found {len(errors)} parse error(s):\n" + "\n".join(errors[:10])
            )

        return orders

    @classmethod
    def load_with_timestamps(cls, path: str | Path) -> list[tuple[datetime | None, Order]]:
        """
        Load orders along with their optional replay timestamps.

        Returns list of (timestamp_or_None, Order) pairs.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Replay file not found: {path}")

        result: list[tuple[datetime | None, Order]] = []

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise CSVParseError("CSV file has no header row")

            for row in reader:
                order = cls._parse_row(row)
                ts = cls._parse_timestamp(row.get("timestamp", ""))
                result.append((ts, order))

        return result

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @classmethod
    def _parse_row(cls, row: dict) -> Order:
        """Convert one CSV row dict into an Order."""
        # Normalise keys to lowercase
        row = {k.strip().lower(): v.strip() for k, v in row.items()}

        side_str = row.get("side", "").upper()
        if side_str not in cls.SIDE_MAP:
            raise ValueError(f"Unknown side: '{side_str}' (expected BUY/SELL)")
        side = cls.SIDE_MAP[side_str]

        type_str = row.get("order_type", "").upper()
        if type_str not in cls.TYPE_MAP:
            raise ValueError(f"Unknown order_type: '{type_str}'")
        order_type = cls.TYPE_MAP[type_str]

        qty_str = row.get("quantity", "0")
        try:
            quantity = int(qty_str)
        except ValueError:
            raise ValueError(f"Invalid quantity: '{qty_str}'")

        price: float | None = None
        price_str = row.get("price", "").strip()
        if price_str and price_str.lower() not in ("", "none", "nan"):
            try:
                price = float(price_str)
            except ValueError:
                raise ValueError(f"Invalid price: '{price_str}'")

        symbol = row.get("symbol", "AAPL") or "AAPL"
        trader_id = row.get("trader_id", "replay") or "replay"
        order_id = row.get("order_id", "") or str(uuid.uuid4())

        # Build TIF from order_type
        tif_str = row.get("time_in_force", type_str).upper()
        tif = cls.TIF_MAP.get(tif_str, TimeInForce.GTC)

        now = datetime.now(timezone.utc)
        return Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            time_in_force=tif,
            price=price,
            quantity=quantity,
            remaining_qty=quantity,
            created_at=now,
            updated_at=now,
            status=__import__("exchange.orders.enums", fromlist=["OrderStatus"]).OrderStatus.NEW,
            trader_id=trader_id,
            client_order_id=row.get("client_order_id", ""),
        )

    @staticmethod
    def _parse_timestamp(ts_str: str) -> datetime | None:
        """Parse a timestamp string into a datetime, or None if not provided."""
        if not ts_str or ts_str.lower() in ("", "none", "nan"):
            return None
        try:
            # Try Unix timestamp
            return datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
        except ValueError:
            pass
        try:
            # Try ISO 8601
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            return None
