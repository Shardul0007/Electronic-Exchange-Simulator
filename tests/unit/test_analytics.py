"""
Unit tests for analytics metrics, latency tracker, and order flow analyzer.
"""

import time
import pytest
from datetime import datetime, timezone, timedelta

from exchange.analytics.metrics import (
    compute_vwap,
    compute_rolling_vwap,
    compute_spread,
    compute_mid_price,
    compute_relative_spread,
    compute_imbalance,
    compute_fill_rate,
    compute_avg_execution_price,
    compute_total_volume,
    compute_total_notional,
    compute_price_volatility,
    estimate_market_impact,
    compute_volume_profile,
)
from exchange.analytics.latency import LatencyTracker
from exchange.analytics.flow import OrderFlowAnalyzer
from exchange.orders.models import Trade, ExecutionReport, Order
from exchange.orders.enums import ExecType, OrderSide, OrderType, TimeInForce, OrderStatus


def make_trade(price: float, qty: int, offset_seconds: int = 0) -> Trade:
    ts = datetime(2024, 1, 1, 9, 30, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_seconds)
    return Trade(
        trade_id=f"t-{price}-{qty}",
        symbol="AAPL",
        price=price,
        quantity=qty,
        buy_order_id="b",
        sell_order_id="s",
        buyer_trader_id="buyer",
        seller_trader_id="seller",
        executed_at=ts,
    )


def make_report(
    exec_type: ExecType = ExecType.NEW,
    side: OrderSide = OrderSide.BUY,
    qty: int = 100,
    trader: str = "t1",
) -> ExecutionReport:
    now = datetime.now(timezone.utc)
    return ExecutionReport(
        exec_id="e1",
        order_id="o1",
        symbol="AAPL",
        exec_type=exec_type,
        order_status=OrderStatus.NEW,
        order_side=side,
        order_type=OrderType.LIMIT,
        order_qty=qty,
        filled_qty=0,
        remaining_qty=qty,
        last_fill_qty=0,
        last_fill_price=0.0,
        avg_fill_price=0.0,
        timestamp=now,
        trader_id=trader,
    )


class TestVWAP:
    def test_single_trade(self):
        trades = [make_trade(100.0, 50)]
        assert compute_vwap(trades) == pytest.approx(100.0)

    def test_two_trades_equal_volume(self):
        trades = [make_trade(100.0, 50), make_trade(102.0, 50)]
        assert compute_vwap(trades) == pytest.approx(101.0)

    def test_two_trades_unequal_volume(self):
        trades = [make_trade(100.0, 100), make_trade(110.0, 10)]
        # VWAP = (100*100 + 110*10) / 110 = 11100 / 110 ≈ 100.909
        assert compute_vwap(trades) == pytest.approx(11100 / 110)

    def test_empty_trades_returns_none(self):
        assert compute_vwap([]) is None

    def test_rolling_vwap(self):
        trades = [make_trade(100.0 + i, 10, i) for i in range(10)]
        results = compute_rolling_vwap(trades, window=3)
        assert len(results) == 10
        assert all(isinstance(ts, datetime) for ts, _ in results)


class TestSpreadMidPrice:
    def test_spread(self):
        assert compute_spread(100.0, 102.0) == pytest.approx(2.0)

    def test_spread_none_if_missing(self):
        assert compute_spread(None, 102.0) is None
        assert compute_spread(100.0, None) is None

    def test_mid_price(self):
        assert compute_mid_price(100.0, 102.0) == pytest.approx(101.0)

    def test_mid_price_none_if_missing(self):
        assert compute_mid_price(None, 102.0) is None

    def test_relative_spread(self):
        # spread=2, mid=101 → relative=2/101
        result = compute_relative_spread(100.0, 102.0)
        assert result == pytest.approx(2.0 / 101.0)

    def test_relative_spread_none_for_empty_side(self):
        assert compute_relative_spread(None, 102.0) is None


class TestImbalance:
    def test_balanced(self):
        assert compute_imbalance(50, 50) == pytest.approx(0.0)

    def test_all_bids(self):
        assert compute_imbalance(100, 0) == pytest.approx(1.0)

    def test_all_asks(self):
        assert compute_imbalance(0, 100) == pytest.approx(-1.0)

    def test_empty_returns_none(self):
        assert compute_imbalance(0, 0) is None

    def test_buy_heavy(self):
        imb = compute_imbalance(80, 20)
        assert imb == pytest.approx(0.6)


class TestFillRate:
    def test_full_fill(self):
        assert compute_fill_rate(100, 100) == pytest.approx(1.0)

    def test_zero_orders(self):
        assert compute_fill_rate(0, 0) == pytest.approx(0.0)

    def test_partial_fill(self):
        assert compute_fill_rate(100, 60) == pytest.approx(0.6)


class TestVolume:
    def test_total_volume(self):
        trades = [make_trade(100.0, 50), make_trade(101.0, 30)]
        assert compute_total_volume(trades) == 80

    def test_total_notional(self):
        trades = [make_trade(100.0, 50), make_trade(101.0, 30)]
        assert compute_total_notional(trades) == pytest.approx(100*50 + 101*30)

    def test_avg_execution_price(self):
        trades = [make_trade(100.0, 10), make_trade(102.0, 10)]
        assert compute_avg_execution_price(trades) == pytest.approx(101.0)

    def test_avg_execution_price_empty_none(self):
        assert compute_avg_execution_price([]) is None

    def test_volume_profile(self):
        trades = [make_trade(100.0, 10, i * 60) for i in range(5)]
        profile = compute_volume_profile(trades, bucket_size_minutes=1)
        assert sum(profile.values()) == 50


class TestPriceVolatility:
    def test_volatility(self):
        trades = [make_trade(p, 10) for p in [100.0, 101.0, 99.0, 102.0]]
        vol = compute_price_volatility(trades)
        assert vol is not None
        assert vol > 0

    def test_single_trade_returns_none(self):
        assert compute_price_volatility([make_trade(100.0, 10)]) is None

    def test_empty_returns_none(self):
        assert compute_price_volatility([]) is None


class TestMarketImpact:
    def test_positive_drift(self):
        trades = [make_trade(100.0, 10), make_trade(101.0, 10), make_trade(102.0, 10)]
        result = estimate_market_impact(trades)
        assert result["impact"] == pytest.approx(2.0)
        assert result["drift_pct"] > 0

    def test_single_trade(self):
        result = estimate_market_impact([make_trade(100.0, 10)])
        assert result["impact"] is None


class TestLatencyTracker:
    def test_basic_tracking(self):
        tracker = LatencyTracker()
        tracker.record_submit("order-1")
        time.sleep(0.001)  # 1ms
        latency = tracker.record_complete("order-1")
        assert latency is not None
        assert latency >= 1000  # At least 1000 µs = 1ms

    def test_unknown_order_returns_none(self):
        tracker = LatencyTracker()
        assert tracker.record_complete("unknown") is None

    def test_stats_percentiles(self):
        tracker = LatencyTracker()
        for i in range(100):
            tracker.add_sample_us(f"order-{i}", float(i + 1))
        stats = tracker.get_stats()
        assert stats["count"] == 100
        assert "p99_us" in stats
        assert stats["min_us"] < stats["max_us"]

    def test_histogram(self):
        tracker = LatencyTracker()
        for i in range(50):
            tracker.add_sample_us(f"o{i}", float(i))
        hist = tracker.get_histogram(bins=10)
        assert len(hist["edges"]) == 11
        assert sum(hist["counts"]) == 50

    def test_reset_clears(self):
        tracker = LatencyTracker()
        tracker.add_sample_us("o1", 100.0)
        tracker.reset()
        assert len(tracker) == 0


class TestOrderFlowAnalyzer:
    def setup_method(self):
        self.analyzer = OrderFlowAnalyzer()
        # Ingest sample reports
        self.analyzer.ingest_reports([
            make_report(ExecType.NEW, OrderSide.BUY, 100),
            make_report(ExecType.NEW, OrderSide.BUY, 200),
            make_report(ExecType.NEW, OrderSide.SELL, 150),
        ])

    def test_buy_sell_ratio(self):
        result = self.analyzer.buy_sell_ratio()
        assert result["buy_count"] == 2
        assert result["sell_count"] == 1
        assert result["buy_fraction"] == pytest.approx(2 / 3)

    def test_size_distribution(self):
        dist = self.analyzer.order_size_distribution()
        assert dist["count"] == 3
        assert dist["min"] == 100
        assert dist["max"] == 200
