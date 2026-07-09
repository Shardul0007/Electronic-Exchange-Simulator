"""
Price-Time Priority Matching Engine.

Implements the matching algorithm used by modern electronic exchanges:
  1. Orders are matched at the best available price (price priority).
  2. At the same price, orders are matched in arrival order (time priority).

Supports order types:
  - LIMIT  : Rest in book if not immediately marketable.
  - MARKET : Execute at best available price; cancel remainder if book exhausted.
  - IOC    : Immediate-or-Cancel — fill as much as possible, cancel residual.
  - FOK    : Fill-or-Kill — fill entirely or cancel entirely.
  - GTC    : Same as LIMIT; alias kept for FIX compatibility.

Self-trade prevention:
  Orders from the same trader_id do not match against each other.
  The engine skips self-trades silently (mimics "cancel" prevention mode).

Execution report lifecycle:
  NEW     → order accepted and resting (LIMIT/GTC)
  PARTIAL_FILL → order partially filled
  FILL    → order fully filled
  CANCELLED → IOC remainder, FOK no-fill, or explicit cancel
  REJECTED  → validation failure (from Exchange layer, not engine)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from exchange.interfaces.base_engine import IMatchingEngine
from exchange.matching.order_book import LimitOrderBook
from exchange.orders.enums import ExecType, OrderSide, OrderStatus, OrderType
from exchange.orders.models import ExecutionReport, Order, Trade


@dataclass
class MatchResult:
    """Container for all outputs of a single matching attempt."""

    trades: list[Trade] = field(default_factory=list)
    reports: list[ExecutionReport] = field(default_factory=list)


class MatchingEngine(IMatchingEngine):
    """
    Price-time priority matching engine.

    Injected with a LimitOrderBook (Dependency Injection).
    Can be reset between simulations without creating a new exchange.
    """

    def __init__(self, book: LimitOrderBook, enable_self_trade_prevention: bool = True) -> None:
        self._book: LimitOrderBook = book
        self._enable_stp: bool = enable_self_trade_prevention
        self._trades: list[Trade] = []
        self._all_reports: list[ExecutionReport] = []

        # Tracks cumulative fill value per order_id for avg fill price
        # { order_id: (total_notional, total_filled_qty) }
        self._fill_tracker: dict[str, tuple[float, int]] = {}

    # -----------------------------------------------------------------------
    # IMatchingEngine interface
    # -----------------------------------------------------------------------

    def submit_order(self, order: Order) -> list[ExecutionReport]:
        """
        Submit an order for matching.

        Entry point called by the Exchange after validation.
        Returns all ExecutionReports generated for this order.
        """
        reports: list[ExecutionReport] = []

        if order.order_type == OrderType.FOK:
            reports = self._handle_fok(order)
        elif order.order_type in (OrderType.MARKET, OrderType.IOC):
            reports = self._handle_ioc_or_market(order)
        else:
            # LIMIT or GTC — may partially fill then rest
            reports = self._handle_limit(order)

        self._all_reports.extend(reports)
        return reports

    def cancel_order(self, order_id: str) -> ExecutionReport | None:
        """Cancel a live resting order."""
        order = self._book.cancel_order(order_id)
        if order is None:
            return None
        order.cancel()
        report = ExecutionReport.cancel_report(order)
        self._all_reports.append(report)
        return report

    def modify_order(
        self, order_id: str, new_quantity: int, new_price: float | None = None
    ) -> ExecutionReport | None:
        """
        Modify quantity (and optionally price) of a resting order.

        If price changes: cancel old order + re-insert (loses time priority).
        If only quantity changes: modify in-place (preserves time priority).
        """
        order = self._book.get_order(order_id)
        if order is None:
            return None

        if new_price is not None and new_price != order.price:
            # Price change: cancel + re-insert (resets time priority)
            self._book.cancel_order(order_id)
            order.modify(new_qty=new_quantity, new_price=new_price)
            self._book.add_order(order)
        else:
            # Quantity-only change: modify in-place
            self._book.modify_order(order_id, new_quantity=new_quantity)
            order.modify(new_qty=new_quantity)

        report = ExecutionReport.modify_report(order)
        self._all_reports.append(report)
        return report

    def get_trades(self) -> list[Trade]:
        """Return a copy of all trades generated so far."""
        return list(self._trades)

    def reset(self) -> None:
        """Clear engine state and the underlying order book."""
        self._trades.clear()
        self._all_reports.clear()
        self._fill_tracker.clear()
        self._book._bids.clear()
        self._book._asks.clear()
        self._book._order_index.clear()

    # -----------------------------------------------------------------------
    # Order type handlers
    # -----------------------------------------------------------------------

    def _handle_limit(self, order: Order) -> list[ExecutionReport]:
        """Handle a LIMIT or GTC order."""
        reports: list[ExecutionReport] = []

        # Try to match
        self._match_order(order, reports)

        if order.is_active:
            # Residual rests in the book
            self._book.add_order(order)
            if order.status == OrderStatus.NEW:
                reports.append(ExecutionReport.new_order(order))
            # else: PARTIALLY_FILLED and resting — already reported in _match_order

        return reports

    def _handle_ioc_or_market(self, order: Order) -> list[ExecutionReport]:
        """Handle IOC or MARKET orders — fill as much as possible, cancel rest."""
        reports: list[ExecutionReport] = []

        self._match_order(order, reports)

        if order.is_active and order.remaining_qty > 0:
            order.cancel()
            reports.append(ExecutionReport.cancel_report(order, reason="IOC/MARKET residual"))

        return reports

    def _handle_fok(self, order: Order) -> list[ExecutionReport]:
        """
        Handle FOK orders — fill entirely or cancel.

        We first check if the book has enough quantity available at acceptable
        prices, then execute only if fully fillable.
        """
        reports: list[ExecutionReport] = []

        if not self._can_fully_fill(order):
            order.cancel()
            return [ExecutionReport.cancel_report(order, reason="FOK: insufficient liquidity")]

        # Proceed with matching (guaranteed to fill fully)
        self._match_order(order, reports)

        if order.is_active:
            # Should not happen after _can_fully_fill check, but defensive code
            order.cancel()
            reports.append(ExecutionReport.cancel_report(order, reason="FOK: partial fill"))

        return reports

    # -----------------------------------------------------------------------
    # Core matching loop
    # -----------------------------------------------------------------------

    def _match_order(self, incoming: Order, reports: list[ExecutionReport]) -> None:
        """
        Execute the price-time priority matching loop.

        Walks the opposite side of the book and fills at each price level.
        Generates Trade and ExecutionReport objects for each fill.
        """
        opposite_side = incoming.side.opposite

        while incoming.remaining_qty > 0:
            best_level = self._book.get_best_level(opposite_side)
            if best_level is None:
                break  # No liquidity

            resting_price = best_level.price

            # Price cross check
            if not self._prices_cross(incoming, resting_price):
                break

            # Walk the FIFO queue at this price level
            while incoming.remaining_qty > 0 and not best_level.is_empty:
                resting = best_level.peek_front()
                if resting is None:
                    break

                # Self-trade prevention
                if self._enable_stp and incoming.trader_id == resting.trader_id:
                    # Cancel the incoming order (cancel newest)
                    incoming.cancel()
                    incoming.remaining_qty = 0
                    reports.append(ExecutionReport.cancel_report(incoming, reason="Self-trade prevention"))
                    break

                fill_qty = min(incoming.remaining_qty, resting.remaining_qty)
                fill_price = resting.price  # Price-time: resting order sets the price

                # Generate the trade
                trade = self._create_trade(incoming, resting, fill_price, fill_qty)
                self._trades.append(trade)

                # Apply fills
                incoming.fill(fill_qty)
                resting.fill(fill_qty)
                best_level.reduce_qty(fill_qty)

                # Update fill tracker for avg price
                self._record_fill(incoming.order_id, fill_price, fill_qty)
                self._record_fill(resting.order_id, fill_price, fill_qty)

                # Execution reports for both sides
                incoming_avg = self._avg_fill_price(incoming.order_id)
                resting_avg = self._avg_fill_price(resting.order_id)

                reports.append(ExecutionReport.fill_report(incoming, trade, incoming_avg))
                reports.append(ExecutionReport.fill_report(resting, trade, resting_avg))

                # Remove fully filled resting order from queue
                if resting.remaining_qty == 0:
                    best_level.remove_front()
                    self._book._order_index.pop(resting.order_id, None)

            # Remove empty price level from book
            if best_level.is_empty:
                book = self._book._get_book(opposite_side)
                key = self._book._price_key(opposite_side, resting_price)
                if key in book:
                    del book[key]

    # -----------------------------------------------------------------------
    # FOK helpers
    # -----------------------------------------------------------------------

    def _can_fully_fill(self, order: Order) -> bool:
        """
        Check if the book has enough liquidity to fully fill the FOK order.

        Does NOT modify any state.
        """
        needed = order.remaining_qty
        opposite_side = order.side.opposite
        book = self._book._get_book(opposite_side)

        for key, level in book.items():
            resting_price = level.price
            if not self._prices_cross(order, resting_price):
                break
            needed -= level.total_qty
            if needed <= 0:
                return True

        return False

    # -----------------------------------------------------------------------
    # Price cross logic
    # -----------------------------------------------------------------------

    @staticmethod
    def _prices_cross(incoming: Order, resting_price: float) -> bool:
        """
        Return True if the incoming order price crosses the resting price.

        Buy crosses if incoming.price >= resting (ask) price.
        Sell crosses if incoming.price <= resting (bid) price.
        Market orders always cross.
        """
        if incoming.price is None:  # MARKET order
            return True
        if incoming.side == OrderSide.BUY:
            return incoming.price >= resting_price
        else:
            return incoming.price <= resting_price

    # -----------------------------------------------------------------------
    # Trade creation
    # -----------------------------------------------------------------------

    @staticmethod
    def _create_trade(
        incoming: Order, resting: Order, price: float, qty: int
    ) -> Trade:
        """Create a Trade given the incoming and resting orders."""
        if incoming.side == OrderSide.BUY:
            buy_order, sell_order = incoming, resting
        else:
            buy_order, sell_order = resting, incoming

        return Trade.create(
            symbol=incoming.symbol,
            price=price,
            quantity=qty,
            buy_order_id=buy_order.order_id,
            sell_order_id=sell_order.order_id,
            buyer_trader_id=buy_order.trader_id,
            seller_trader_id=sell_order.trader_id,
        )

    # -----------------------------------------------------------------------
    # Fill tracking (for avg fill price)
    # -----------------------------------------------------------------------

    def _record_fill(self, order_id: str, price: float, qty: int) -> None:
        notional, filled = self._fill_tracker.get(order_id, (0.0, 0))
        self._fill_tracker[order_id] = (notional + price * qty, filled + qty)

    def _avg_fill_price(self, order_id: str) -> float:
        notional, filled = self._fill_tracker.get(order_id, (0.0, 0))
        return notional / filled if filled > 0 else 0.0

    # -----------------------------------------------------------------------
    # Queries
    # -----------------------------------------------------------------------

    @property
    def book(self) -> LimitOrderBook:
        """Access to the underlying order book."""
        return self._book

    @property
    def trade_count(self) -> int:
        return len(self._trades)

    @property
    def total_volume(self) -> int:
        return sum(t.quantity for t in self._trades)

    @property
    def total_notional(self) -> float:
        return sum(t.notional for t in self._trades)

    def vwap(self) -> float | None:
        """VWAP of all trades in this session."""
        if not self._trades:
            return None
        return self.total_notional / self.total_volume

    def __repr__(self) -> str:
        return (
            f"MatchingEngine({self._book.symbol}, "
            f"trades={self.trade_count}, volume={self.total_volume})"
        )
