"""
Market data publisher.

Maintains and broadcasts the current L1/L2 order book state.
In a real exchange, this would push snapshots over a multicast UDP feed
(e.g., ITCH or PITCH protocol). Here we maintain the latest snapshot
in memory for the dashboard and analytics to consume.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class MarketDataPublisher:
    """
    Maintains the latest market data snapshot for a symbol.

    Subscribers (analytics, dashboard) call `get_latest()` to read
    the current book state without knowing about the book internals.
    """

    def __init__(self, symbol: str) -> None:
        self._symbol: str = symbol
        self._latest: dict[str, Any] = {}
        self._history: list[dict[str, Any]] = []
        self._tick_count: int = 0

    def publish_snapshot(self, depth: dict) -> None:
        """
        Publish a new order book snapshot.

        Called by the Exchange after every order submission, cancel, or modify.
        """
        snapshot = {
            **depth,
            "tick": self._tick_count,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        self._latest = snapshot
        self._history.append(snapshot)
        self._tick_count += 1

    def get_latest(self) -> dict:
        """Return the most recent published snapshot."""
        return dict(self._latest)

    def get_history(self, last_n: int | None = None) -> list[dict]:
        """Return the snapshot history, optionally trimmed to last_n entries."""
        if last_n is None:
            return list(self._history)
        return list(self._history[-last_n:])

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def reset(self) -> None:
        self._latest = {}
        self._history.clear()
        self._tick_count = 0
