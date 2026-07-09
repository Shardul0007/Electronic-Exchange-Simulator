"""
High-Performance Electronic Exchange Simulator

A production-grade Python implementation of a modern electronic exchange,
implementing price-time priority matching, realistic order lifecycle
management, and market microstructure analytics.

Architecture overview:
  exchange/
    interfaces/   — Abstract base classes (contracts)
    orders/       — Order models, enums, validation
    matching/     — Order book and matching engine
    core/         — Exchange facade, market data, execution history
    replay/       — Historical order replay engine
    analytics/    — Market microstructure metrics
    reporting/    — JSON, CSV, HTML report generation
    dashboard/    — Interactive Plotly Dash dashboard
"""

__version__ = "1.0.0"
__author__ = "Shardul"
