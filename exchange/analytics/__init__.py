"""Analytics package public API."""

from exchange.analytics.flow import OrderFlowAnalyzer
from exchange.analytics.latency import LatencyTracker, LatencySample
from exchange.analytics.metrics import (
    compute_avg_execution_price,
    compute_fill_rate,
    compute_imbalance,
    compute_imbalance_from_depth,
    compute_market_depth,
    compute_mid_price,
    compute_price_volatility,
    compute_relative_spread,
    compute_rolling_vwap,
    compute_spread,
    compute_total_notional,
    compute_total_volume,
    compute_volume_profile,
    compute_vwap,
    estimate_market_impact,
)

__all__ = [
    # Metrics
    "compute_vwap",
    "compute_rolling_vwap",
    "compute_spread",
    "compute_mid_price",
    "compute_relative_spread",
    "compute_market_depth",
    "compute_imbalance",
    "compute_imbalance_from_depth",
    "compute_fill_rate",
    "compute_avg_execution_price",
    "compute_total_volume",
    "compute_total_notional",
    "compute_volume_profile",
    "estimate_market_impact",
    "compute_price_volatility",
    # Classes
    "LatencyTracker",
    "LatencySample",
    "OrderFlowAnalyzer",
]
