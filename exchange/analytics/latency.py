"""
Execution latency tracking and analysis.

Tracks the round-trip latency from order submission to final execution report
and provides percentile statistics for performance analysis.

In production, this would use hardware timestamps (RDTSC) or kernel-bypass
networking timestamps. In simulation, we use `time.perf_counter_ns()`.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field


@dataclass
class LatencySample:
    """A single latency measurement."""
    order_id: str
    submit_ns: int      # time.perf_counter_ns() at submission
    complete_ns: int    # time.perf_counter_ns() at last report

    @property
    def latency_us(self) -> float:
        """Latency in microseconds."""
        return (self.complete_ns - self.submit_ns) / 1_000.0


class LatencyTracker:
    """
    Tracks execution latencies for all orders.

    Usage:
        tracker = LatencyTracker()
        t_start = tracker.record_submit("order-123")
        # ... matching ...
        tracker.record_complete("order-123")
        stats = tracker.get_stats()
    """

    def __init__(self) -> None:
        self._pending: dict[str, int] = {}  # order_id → submit_ns
        self._samples: list[LatencySample] = []

    def record_submit(self, order_id: str) -> int:
        """Record submission time. Returns the timestamp in nanoseconds."""
        ns = time.perf_counter_ns()
        self._pending[order_id] = ns
        return ns

    def record_complete(self, order_id: str) -> float | None:
        """
        Record completion time and compute latency.

        Returns latency in microseconds, or None if order not found.
        """
        if order_id not in self._pending:
            return None
        submit_ns = self._pending.pop(order_id)
        complete_ns = time.perf_counter_ns()
        sample = LatencySample(order_id, submit_ns, complete_ns)
        self._samples.append(sample)
        return sample.latency_us

    def add_sample_us(self, order_id: str, latency_us: float) -> None:
        """Add a pre-computed latency sample in microseconds."""
        now_ns = time.perf_counter_ns()
        submit_ns = now_ns - int(latency_us * 1_000)
        self._samples.append(LatencySample(order_id, submit_ns, now_ns))

    def get_stats(self) -> dict:
        """Compute latency statistics in microseconds."""
        if not self._samples:
            return {}
        latencies = sorted(s.latency_us for s in self._samples)
        n = len(latencies)
        return {
            "count": n,
            "min_us": round(latencies[0], 3),
            "max_us": round(latencies[-1], 3),
            "mean_us": round(statistics.mean(latencies), 3),
            "median_us": round(statistics.median(latencies), 3),
            "stdev_us": round(statistics.stdev(latencies), 3) if n > 1 else 0.0,
            "p50_us": round(latencies[int(n * 0.50)], 3),
            "p75_us": round(latencies[int(n * 0.75)], 3),
            "p90_us": round(latencies[int(n * 0.90)], 3),
            "p95_us": round(latencies[int(n * 0.95)], 3),
            "p99_us": round(latencies[int(n * 0.99)], 3),
        }

    def get_all_latencies_us(self) -> list[float]:
        """Return all latency samples in microseconds (sorted)."""
        return sorted(s.latency_us for s in self._samples)

    def get_histogram(self, bins: int = 20) -> dict:
        """
        Compute a simple histogram of latency samples.

        Returns {'edges': [...], 'counts': [...]} for plotting.
        """
        if not self._samples:
            return {"edges": [], "counts": []}

        latencies = self.get_all_latencies_us()
        min_v, max_v = latencies[0], latencies[-1]

        if min_v == max_v:
            return {"edges": [min_v, max_v], "counts": [len(latencies)]}

        width = (max_v - min_v) / bins
        counts = [0] * bins
        edges = [min_v + i * width for i in range(bins + 1)]

        for lat in latencies:
            idx = min(int((lat - min_v) / width), bins - 1)
            counts[idx] += 1

        return {"edges": [round(e, 3) for e in edges], "counts": counts}

    def reset(self) -> None:
        self._pending.clear()
        self._samples.clear()

    def __len__(self) -> int:
        return len(self._samples)
