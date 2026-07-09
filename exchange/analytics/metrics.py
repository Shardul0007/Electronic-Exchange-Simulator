"""
Market microstructure analytics — pure functions.

All functions are stateless and operate on lists of Trade objects
or order book depth snapshots. Pure functions are:
  - Deterministic (same inputs → same output)
  - Independently testable (no hidden state)
  - Thread-safe (no shared mutable state)

Metrics implemented:
  - VWAP (Volume-Weighted Average Price)
  - Mid Price
  - Bid-Ask Spread
  - Market Depth
  - Order Book Imbalance
  - Fill Rate
  - Average Execution Price
  - Trade Volume (total and per-window)
  - Liquidity metrics (market impact estimate)
"""

from __future__ import annotations

import statistics
from datetime import datetime

from exchange.orders.models import Trade


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------

def compute_vwap(trades: list[Trade]) -> float | None:
    """
    Volume-Weighted Average Price.

    VWAP = Σ(price_i × qty_i) / Σ(qty_i)

    Returns None if there are no trades.
    """
    if not trades:
        return None
    total_notional = sum(t.price * t.quantity for t in trades)
    total_volume = sum(t.quantity for t in trades)
    return total_notional / total_volume if total_volume > 0 else None


def compute_rolling_vwap(
    trades: list[Trade], window: int = 20
) -> list[tuple[datetime, float]]:
    """
    Rolling VWAP over the last `window` trades.

    Returns a list of (timestamp, vwap) pairs.
    """
    if not trades:
        return []

    results: list[tuple[datetime, float]] = []
    for i in range(1, len(trades) + 1):
        window_trades = trades[max(0, i - window) : i]
        vwap = compute_vwap(window_trades)
        if vwap is not None:
            results.append((trades[i - 1].executed_at, vwap))
    return results


# ---------------------------------------------------------------------------
# Spread & Mid Price
# ---------------------------------------------------------------------------

def compute_spread(best_bid: float | None, best_ask: float | None) -> float | None:
    """Bid-ask spread = best_ask - best_bid."""
    if best_bid is None or best_ask is None:
        return None
    return round(best_ask - best_bid, 10)


def compute_mid_price(best_bid: float | None, best_ask: float | None) -> float | None:
    """Mid price = (best_bid + best_ask) / 2."""
    if best_bid is None or best_ask is None:
        return None
    return (best_bid + best_ask) / 2.0


def compute_relative_spread(
    best_bid: float | None, best_ask: float | None
) -> float | None:
    """
    Relative spread = (ask - bid) / mid_price.

    Normalises spread by price level for cross-asset comparison.
    """
    spread = compute_spread(best_bid, best_ask)
    mid = compute_mid_price(best_bid, best_ask)
    if spread is None or mid is None or mid == 0:
        return None
    return spread / mid


# ---------------------------------------------------------------------------
# Market Depth
# ---------------------------------------------------------------------------

def compute_market_depth(depth: dict, levels: int = 5) -> dict:
    """
    Summarise order book depth at up to `levels` price levels.

    Returns total bid volume, total ask volume, and per-level data.
    """
    bids = depth.get("bids", [])[:levels]
    asks = depth.get("asks", [])[:levels]

    total_bid_vol = sum(b["total_qty"] for b in bids)
    total_ask_vol = sum(a["total_qty"] for a in asks)

    return {
        "bid_levels": len(bids),
        "ask_levels": len(asks),
        "total_bid_volume": total_bid_vol,
        "total_ask_volume": total_ask_vol,
        "bid_levels_data": bids,
        "ask_levels_data": asks,
    }


# ---------------------------------------------------------------------------
# Order Book Imbalance
# ---------------------------------------------------------------------------

def compute_imbalance(bid_volume: int, ask_volume: int) -> float | None:
    """
    Order book imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol).

    Returns a value in [-1, +1]:
      +1: all volume is on the bid side (extreme buy pressure)
      -1: all volume is on the ask side (extreme sell pressure)
       0: balanced book
    """
    total = bid_volume + ask_volume
    if total == 0:
        return None
    return (bid_volume - ask_volume) / total


def compute_imbalance_from_depth(depth: dict, levels: int = 5) -> float | None:
    """Compute imbalance directly from a depth snapshot."""
    bids = depth.get("bids", [])[:levels]
    asks = depth.get("asks", [])[:levels]
    bid_vol = sum(b["total_qty"] for b in bids)
    ask_vol = sum(a["total_qty"] for a in asks)
    return compute_imbalance(bid_vol, ask_vol)


# ---------------------------------------------------------------------------
# Fill Rate & Execution Quality
# ---------------------------------------------------------------------------

def compute_fill_rate(total_orders: int, filled_orders: int) -> float:
    """
    Fraction of submitted orders that received at least one fill.

    Range: [0.0, 1.0]
    """
    if total_orders == 0:
        return 0.0
    return filled_orders / total_orders


def compute_avg_execution_price(trades: list[Trade]) -> float | None:
    """Simple average execution price (unweighted by quantity)."""
    if not trades:
        return None
    return sum(t.price for t in trades) / len(trades)


# ---------------------------------------------------------------------------
# Volume & Notional
# ---------------------------------------------------------------------------

def compute_total_volume(trades: list[Trade]) -> int:
    """Total traded quantity."""
    return sum(t.quantity for t in trades)


def compute_total_notional(trades: list[Trade]) -> float:
    """Total traded notional value (price × quantity)."""
    return sum(t.notional for t in trades)


def compute_volume_profile(
    trades: list[Trade], bucket_size_minutes: int = 1
) -> dict[str, int]:
    """
    Aggregate trade volume into time buckets.

    Returns a dict of ISO-timestamp (bucket start) → total volume.
    """
    if not trades:
        return {}

    from datetime import timedelta

    buckets: dict[str, int] = {}
    bucket_td = timedelta(minutes=bucket_size_minutes)

    for trade in trades:
        ts = trade.executed_at
        # Floor to nearest bucket
        bucket_start = ts - timedelta(
            minutes=ts.minute % bucket_size_minutes,
            seconds=ts.second,
            microseconds=ts.microsecond,
        )
        key = bucket_start.isoformat()
        buckets[key] = buckets.get(key, 0) + trade.quantity

    return dict(sorted(buckets.items()))


# ---------------------------------------------------------------------------
# Liquidity Metrics
# ---------------------------------------------------------------------------

def estimate_market_impact(
    trades: list[Trade], reference_price: float | None = None
) -> dict:
    """
    Estimate market impact as price drift from first to last trade.

    A simple implementation: real market impact models (Almgren-Chriss,
    Kyle's lambda) require more data, but this gives a directional sense.
    """
    if len(trades) < 2:
        return {"impact": None, "drift_pct": None}

    first_price = trades[0].price
    last_price = trades[-1].price
    ref = reference_price or first_price

    impact = last_price - first_price
    drift_pct = (impact / ref) * 100.0 if ref != 0 else None

    return {
        "first_price": first_price,
        "last_price": last_price,
        "impact": round(impact, 4),
        "drift_pct": round(drift_pct, 4) if drift_pct is not None else None,
    }


def compute_price_volatility(trades: list[Trade]) -> float | None:
    """
    Standard deviation of trade prices (a simple realised volatility proxy).

    Returns None if fewer than 2 trades.
    """
    if len(trades) < 2:
        return None
    prices = [t.price for t in trades]
    return statistics.stdev(prices)
