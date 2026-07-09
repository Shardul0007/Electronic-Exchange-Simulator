"""
Exchange interfaces package.

All abstract base classes (ABCs) defining the contracts between components.
Follows the Dependency Inversion Principle: high-level modules depend on
abstractions, not concrete implementations.
"""

from exchange.interfaces.base_book import IOrderBook
from exchange.interfaces.base_engine import IMatchingEngine
from exchange.interfaces.base_exchange import IAnalyticsEngine, IExchange, IMarketDataPublisher

__all__ = [
    "IOrderBook",
    "IMatchingEngine",
    "IExchange",
    "IMarketDataPublisher",
    "IAnalyticsEngine",
]
