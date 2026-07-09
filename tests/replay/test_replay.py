"""
Tests for the Replay Engine.

Tests:
  - CSV loading (valid, invalid, missing columns)
  - Instant replay correctness
  - Determinism: same CSV → same result
  - Result statistics accuracy
"""

import csv
import os
import tempfile
import pytest

from exchange.core.exchange import Exchange
from exchange.orders.enums import OrderSide, OrderType, ReplaySpeed
from exchange.replay.engine import ReplayEngine
from exchange.replay.loader import CSVParseError, ReplayLoader


SAMPLE_CSV = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "sample_orders.csv"
)


def make_temp_csv(rows: list[dict], tmp_dir: str) -> str:
    """Write rows to a temp CSV file and return its path."""
    path = os.path.join(tmp_dir, "test_orders.csv")
    if not rows:
        with open(path, "w") as f:
            f.write("side,order_type,quantity\n")
        return path
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


class TestReplayLoader:
    def test_load_sample_csv(self):
        orders = ReplayLoader.load(SAMPLE_CSV)
        assert len(orders) == 1200
        assert all(o.quantity > 0 for o in orders)

    def test_all_order_types_parsed(self):
        orders = ReplayLoader.load(SAMPLE_CSV)
        types = {o.order_type for o in orders}
        assert OrderType.LIMIT in types
        assert OrderType.MARKET in types

    def test_market_orders_have_no_price(self):
        orders = ReplayLoader.load(SAMPLE_CSV)
        market_orders = [o for o in orders if o.order_type == OrderType.MARKET]
        assert all(o.price is None for o in market_orders)

    def test_limit_orders_have_price(self):
        orders = ReplayLoader.load(SAMPLE_CSV)
        limit_orders = [o for o in orders if o.order_type == OrderType.LIMIT]
        assert all(o.price is not None for o in limit_orders)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            ReplayLoader.load("nonexistent_file.csv")

    def test_missing_required_columns_raises(self, tmp_path):
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("price,quantity\n100.0,50\n")
        with pytest.raises(CSVParseError, match="required columns"):
            ReplayLoader.load(str(bad_csv))

    def test_invalid_quantity_raises(self, tmp_path):
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("side,order_type,quantity\nBUY,LIMIT,abc\n")
        with pytest.raises(CSVParseError, match="parse error"):
            ReplayLoader.load(str(bad_csv))

    def test_invalid_side_raises(self, tmp_path):
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("side,order_type,quantity\nXXX,LIMIT,100\n")
        with pytest.raises(CSVParseError, match="parse error"):
            ReplayLoader.load(str(bad_csv))

    def test_load_with_timestamps(self):
        timed = ReplayLoader.load_with_timestamps(SAMPLE_CSV)
        assert len(timed) == 1200
        # All entries should have timestamps (sample CSV has them)
        timestamps = [ts for ts, _ in timed]
        assert any(ts is not None for ts in timestamps)


class TestReplayEngine:
    def test_instant_replay_sample_csv(self):
        ex = Exchange(symbol="AAPL")
        engine = ReplayEngine(ex)
        result = engine.replay_csv(SAMPLE_CSV, speed=ReplaySpeed.INSTANT)
        assert result.orders_submitted == 1200
        assert result.total_trades >= 0
        assert result.elapsed_seconds > 0
        assert result.throughput_per_sec > 0

    def test_replay_is_deterministic(self):
        """Same CSV replayed twice must produce identical results."""
        ex1 = Exchange(symbol="AAPL")
        r1 = ReplayEngine(ex1).replay_csv(SAMPLE_CSV, speed=ReplaySpeed.INSTANT)

        ex2 = Exchange(symbol="AAPL")
        r2 = ReplayEngine(ex2).replay_csv(SAMPLE_CSV, speed=ReplaySpeed.INSTANT)

        assert r1.orders_submitted == r2.orders_submitted
        assert r1.total_volume == r2.total_volume
        assert r1.total_notional == pytest.approx(r2.total_notional)

    def test_replay_from_list(self):
        orders = ReplayLoader.load(SAMPLE_CSV)[:100]
        ex = Exchange(symbol="AAPL")
        engine = ReplayEngine(ex)
        result = engine.replay(orders)
        assert result.orders_submitted == 100

    def test_replay_result_summary(self):
        orders = ReplayLoader.load(SAMPLE_CSV)[:50]
        ex = Exchange(symbol="AAPL")
        result = ReplayEngine(ex).replay(orders)
        summary = result.summary()
        assert "orders_submitted" in summary
        assert "total_trades" in summary
        assert "throughput_per_sec" in summary

    def test_replay_reset_exchange(self):
        """Exchange should be reset between replays."""
        orders = ReplayLoader.load(SAMPLE_CSV)[:50]
        ex = Exchange(symbol="AAPL")
        engine = ReplayEngine(ex)

        r1 = engine.replay(orders, reset_exchange=True)
        r2 = engine.replay(orders, reset_exchange=True)

        assert r1.orders_submitted == r2.orders_submitted

    def test_throughput_above_threshold(self):
        """Sanity check: replay should exceed 1000 orders/sec."""
        orders = ReplayLoader.load(SAMPLE_CSV)
        ex = Exchange(symbol="AAPL")
        result = ReplayEngine(ex).replay(orders)
        assert result.throughput_per_sec > 1000
