"""
conftest.py — shared pytest fixtures.
"""
import pytest

from exchange.core.exchange import Exchange
from exchange.matching.engine import MatchingEngine
from exchange.matching.order_book import LimitOrderBook
from exchange.orders.enums import OrderSide
from exchange.orders.models import Order


@pytest.fixture
def book():
    return LimitOrderBook(symbol="TEST")


@pytest.fixture
def engine(book):
    return MatchingEngine(book)


@pytest.fixture
def exchange():
    return Exchange(symbol="TEST")


@pytest.fixture
def limit_buy():
    return Order.create_limit(side=OrderSide.BUY, price=100.0, quantity=100)


@pytest.fixture
def limit_sell():
    return Order.create_limit(side=OrderSide.SELL, price=100.0, quantity=100)
