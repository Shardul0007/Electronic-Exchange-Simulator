"""
Interactive Plotly Dash Dashboard for the Exchange Simulator.

Layout:
  - Header with exchange status
  - Order Book depth (bid/ask bar chart)
  - Trade price & volume timeline
  - Rolling VWAP vs Mid Price
  - Bid-Ask Spread over time
  - Execution latency distribution
  - Order book imbalance gauge
  - Order flow statistics

Run with:
    python -m exchange.dashboard.app
    # Open http://localhost:8050
"""

from __future__ import annotations

import os
import sys

# Add project root to path for module resolution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from exchange.analytics.metrics import (
    compute_imbalance_from_depth,
    compute_mid_price,
    compute_rolling_vwap,
    compute_spread,
)
from exchange.core.exchange import Exchange
from exchange.orders.enums import OrderSide
from exchange.orders.models import Order
from exchange.replay.engine import ReplayEngine
from exchange.replay.loader import ReplayLoader

# ---------------------------------------------------------------------------
# Bootstrap the exchange with sample data
# ---------------------------------------------------------------------------

_SAMPLE_CSV = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "sample_orders.csv"
)


def _bootstrap_exchange() -> Exchange:
    """Load sample data into the exchange for dashboard display."""
    ex = Exchange(symbol="AAPL")
    try:
        orders = ReplayLoader.load(_SAMPLE_CSV)
        ReplayEngine(ex).replay(orders[:500], reset_exchange=False)
    except Exception:
        # Fallback: generate minimal synthetic data
        import random
        random.seed(42)
        for i in range(200):
            side = OrderSide.BUY if i % 2 == 0 else OrderSide.SELL
            price = round(100.0 + random.uniform(-2.0, 2.0), 2)
            qty = random.randint(1, 10) * 10
            try:
                ex.submit_order(Order.create_limit(side, price, qty))
            except Exception:
                pass
    return ex


EXCHANGE = _bootstrap_exchange()

# ---------------------------------------------------------------------------
# Plotly figure builders
# ---------------------------------------------------------------------------

COLOR_BID = "#10b981"   # emerald
COLOR_ASK = "#ef4444"   # red
COLOR_VWAP = "#3b82f6"  # blue
COLOR_MID = "#f59e0b"   # amber
BG_COLOR = "#0a0e1a"
PAPER_COLOR = "#111827"
GRID_COLOR = "#1e2a3a"
TEXT_COLOR = "#94a3b8"

CHART_LAYOUT = dict(
    paper_bgcolor=PAPER_COLOR,
    plot_bgcolor=BG_COLOR,
    font=dict(color=TEXT_COLOR, family="Segoe UI, system-ui"),
    xaxis=dict(gridcolor=GRID_COLOR, linecolor=GRID_COLOR, tickfont=dict(size=11)),
    yaxis=dict(gridcolor=GRID_COLOR, linecolor=GRID_COLOR, tickfont=dict(size=11)),
    margin=dict(l=50, r=20, t=40, b=40),
    showlegend=True,
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
)


def build_order_book_chart(exchange: Exchange) -> go.Figure:
    """Horizontal bid/ask depth bar chart."""
    depth = exchange.book.get_depth(levels=10)
    bids = depth.get("bids", [])
    asks = depth.get("asks", [])

    fig = go.Figure()

    if bids:
        bid_prices = [f"${b['price']:.2f}" for b in bids]
        bid_qtys = [b["total_qty"] for b in bids]
        fig.add_trace(go.Bar(
            x=bid_qtys, y=bid_prices, orientation="h",
            name="Bids", marker_color=COLOR_BID,
            marker_opacity=0.8, hovertemplate="Qty: %{x}<br>Price: %{y}<extra></extra>"
        ))

    if asks:
        ask_prices = [f"${a['price']:.2f}" for a in asks]
        ask_qtys = [a["total_qty"] for a in asks]
        fig.add_trace(go.Bar(
            x=ask_qtys, y=ask_prices, orientation="h",
            name="Asks", marker_color=COLOR_ASK,
            marker_opacity=0.8, hovertemplate="Qty: %{x}<br>Price: %{y}<extra></extra>"
        ))

    fig.update_layout(
        title="Order Book Depth", barmode="overlay", **CHART_LAYOUT,
        xaxis_title="Quantity", yaxis_title="Price",
        height=380,
    )
    return fig


def build_trade_timeline_chart(exchange: Exchange) -> go.Figure:
    """Trade price and volume over time."""
    trades = exchange.get_trades()
    fig = go.Figure()

    if not trades:
        fig.update_layout(title="Trade Timeline (no data)", **CHART_LAYOUT, height=320)
        return fig

    times = [t.executed_at for t in trades]
    prices = [t.price for t in trades]
    volumes = [t.quantity for t in trades]

    fig.add_trace(go.Scatter(
        x=times, y=prices, mode="lines+markers",
        name="Trade Price",
        line=dict(color=COLOR_VWAP, width=2),
        marker=dict(size=5, color=COLOR_VWAP),
        yaxis="y1",
        hovertemplate="Price: $%{y:.2f}<br>Time: %{x}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=times, y=volumes, name="Volume",
        marker_color=COLOR_BID, marker_opacity=0.4,
        yaxis="y2",
        hovertemplate="Vol: %{y}<extra></extra>",
    ))

    fig.update_layout(
        title="Trade Price & Volume Timeline",
        yaxis=dict(title="Price ($)", gridcolor=GRID_COLOR, linecolor=GRID_COLOR,
                   tickfont=dict(size=11), tickprefix="$"),
        yaxis2=dict(title="Volume", overlaying="y", side="right",
                    gridcolor="transparent", tickfont=dict(size=11)),
        xaxis=dict(title="Time", gridcolor=GRID_COLOR),
        **{k: v for k, v in CHART_LAYOUT.items() if k not in ("yaxis",)},
        height=320, paper_bgcolor=PAPER_COLOR, plot_bgcolor=BG_COLOR,
        font=dict(color=TEXT_COLOR), margin=dict(l=60, r=60, t=40, b=40),
        showlegend=True, legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def build_vwap_chart(exchange: Exchange) -> go.Figure:
    """Rolling VWAP vs mid price."""
    trades = exchange.get_trades()
    fig = go.Figure()

    if not trades:
        fig.update_layout(title="VWAP (no data)", **CHART_LAYOUT, height=280)
        return fig

    rolling = compute_rolling_vwap(trades, window=20)
    if rolling:
        vwap_times, vwap_vals = zip(*rolling)
        fig.add_trace(go.Scatter(
            x=list(vwap_times), y=list(vwap_vals),
            mode="lines", name="Rolling VWAP (20)",
            line=dict(color=COLOR_VWAP, width=2.5),
            hovertemplate="VWAP: $%{y:.4f}<extra></extra>",
        ))

    fig.update_layout(
        title="Rolling VWAP", **CHART_LAYOUT,
        yaxis_title="VWAP ($)", xaxis_title="Time", height=280,
    )
    return fig


def build_spread_chart(exchange: Exchange) -> go.Figure:
    """Bid-ask spread over time from book history."""
    history = exchange._publisher.get_history(last_n=200)
    fig = go.Figure()

    if not history:
        fig.update_layout(title="Spread (no data)", **CHART_LAYOUT, height=260)
        return fig

    times = [snap.get("published_at", "") for snap in history]
    spreads = [
        snap.get("spread") for snap in history
        if snap.get("spread") is not None
    ]
    spread_times = [
        snap.get("published_at", "") for snap in history
        if snap.get("spread") is not None
    ]

    if spreads:
        fig.add_trace(go.Scatter(
            x=spread_times, y=spreads,
            mode="lines", name="Bid-Ask Spread",
            line=dict(color=COLOR_MID, width=2),
            fill="tozeroy", fillcolor="rgba(245,158,11,0.1)",
            hovertemplate="Spread: $%{y:.4f}<extra></extra>",
        ))

    fig.update_layout(
        title="Bid-Ask Spread Over Time", **CHART_LAYOUT,
        yaxis_title="Spread ($)", xaxis_title="Tick", height=260,
    )
    return fig


def build_latency_chart(exchange: Exchange) -> go.Figure:
    """Execution latency histogram."""
    latencies = sorted(exchange._latency_us)
    fig = go.Figure()

    if not latencies:
        fig.update_layout(title="Latency Distribution (no data)", **CHART_LAYOUT, height=280)
        return fig

    fig.add_trace(go.Histogram(
        x=latencies, nbinsx=40, name="Latency",
        marker_color=COLOR_VWAP, marker_opacity=0.8,
        hovertemplate="Range: %{x}µs<br>Count: %{y}<extra></extra>",
    ))

    fig.update_layout(
        title="Execution Latency Distribution",
        **CHART_LAYOUT,
        xaxis_title="Latency (µs)", yaxis_title="Count", height=280,
    )
    return fig


def build_imbalance_gauge(exchange: Exchange) -> go.Figure:
    """Order book imbalance gauge."""
    depth = exchange.book.get_depth()
    imb = compute_imbalance_from_depth(depth) or 0.0

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=round(imb * 100, 1),
        title={"text": "Book Imbalance (%)", "font": {"color": TEXT_COLOR, "size": 14}},
        number={"suffix": "%", "font": {"color": TEXT_COLOR}},
        delta={"reference": 0, "relative": False},
        gauge={
            "axis": {"range": [-100, 100], "tickcolor": TEXT_COLOR, "tickfont": {"size": 10}},
            "bar": {"color": COLOR_VWAP},
            "bgcolor": BG_COLOR,
            "borderwidth": 1,
            "bordercolor": GRID_COLOR,
            "steps": [
                {"range": [-100, -33], "color": "rgba(239,68,68,0.2)"},
                {"range": [-33, 33], "color": "rgba(100,100,100,0.1)"},
                {"range": [33, 100], "color": "rgba(16,185,129,0.2)"},
            ],
            "threshold": {"line": {"color": "white", "width": 2}, "thickness": 0.75, "value": imb * 100},
        },
    ))
    fig.update_layout(
        paper_bgcolor=PAPER_COLOR, plot_bgcolor=BG_COLOR,
        font=dict(color=TEXT_COLOR), height=250,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

def kpi_card(label: str, value: str, color: str = "#3b82f6") -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.P(label, className="text-muted mb-1", style={"fontSize": "11px", "textTransform": "uppercase", "letterSpacing": "0.05em"}),
            html.H4(value, style={"color": color, "fontWeight": "700", "margin": 0}),
        ]),
        style={"background": "#111827", "border": "1px solid #2d3a52", "borderRadius": "10px"},
    )


# ---------------------------------------------------------------------------
# App Layout
# ---------------------------------------------------------------------------

def build_layout(exchange: Exchange) -> html.Div:
    summary = exchange.get_summary()
    latency = exchange.get_latency_stats()
    depth = exchange.book.get_depth()

    vwap = summary.get("vwap")
    spread = depth.get("spread")
    mid = depth.get("mid_price")

    return html.Div([
        # ---- Header --------------------------------------------------------
        html.Div([
            html.Div([
                html.H1("⚡ Electronic Exchange Simulator",
                        style={"fontWeight": "800", "fontSize": "22px",
                               "background": "linear-gradient(90deg, #3b82f6, #10b981)",
                               "WebkitBackgroundClip": "text",
                               "WebkitTextFillColor": "transparent"}),
                html.P(f"Symbol: AAPL  |  {summary.get('total_orders', 0):,} orders  |  {summary.get('total_trades', 0):,} trades",
                       style={"color": "#94a3b8", "fontSize": "13px", "marginTop": "4px"}),
            ]),
            html.Div([
                html.Span("● LIVE", style={"color": "#10b981", "fontWeight": "700", "fontSize": "13px"}),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={
            "display": "flex", "justifyContent": "space-between", "alignItems": "center",
            "padding": "20px 32px", "background": "#111827",
            "borderBottom": "1px solid #2d3a52", "marginBottom": "24px",
        }),

        # ---- KPI row -------------------------------------------------------
        html.Div([
            dbc.Row([
                dbc.Col(kpi_card("Total Volume", f"{summary.get('total_volume', 0):,} shares"), width=2),
                dbc.Col(kpi_card("Total Notional", f"${summary.get('total_notional', 0):,.0f}", "#f59e0b"), width=2),
                dbc.Col(kpi_card("VWAP", f"${vwap:.4f}" if vwap else "N/A", "#f59e0b"), width=2),
                dbc.Col(kpi_card("Spread", f"${spread:.4f}" if spread else "N/A", "#3b82f6"), width=2),
                dbc.Col(kpi_card("Fill Rate", f"{summary.get('fill_rate', 0)*100:.1f}%", "#10b981"), width=2),
                dbc.Col(kpi_card("P99 Latency", f"{latency.get('p99_us', 'N/A')}µs" if latency else "N/A", "#94a3b8"), width=2),
            ], className="g-3"),
        ], style={"padding": "0 32px", "marginBottom": "24px"}),

        # ---- Charts row 1 --------------------------------------------------
        html.Div([
            dbc.Row([
                dbc.Col(dcc.Graph(figure=build_order_book_chart(exchange), config={"displayModeBar": False}), width=5),
                dbc.Col(dcc.Graph(figure=build_trade_timeline_chart(exchange), config={"displayModeBar": False}), width=7),
            ], className="g-3"),
        ], style={"padding": "0 32px", "marginBottom": "16px"}),

        # ---- Charts row 2 --------------------------------------------------
        html.Div([
            dbc.Row([
                dbc.Col(dcc.Graph(figure=build_vwap_chart(exchange), config={"displayModeBar": False}), width=4),
                dbc.Col(dcc.Graph(figure=build_spread_chart(exchange), config={"displayModeBar": False}), width=4),
                dbc.Col(dcc.Graph(figure=build_latency_chart(exchange), config={"displayModeBar": False}), width=4),
            ], className="g-3"),
        ], style={"padding": "0 32px", "marginBottom": "16px"}),

        # ---- Row 3: Imbalance + Stats --------------------------------------
        html.Div([
            dbc.Row([
                dbc.Col(dcc.Graph(figure=build_imbalance_gauge(exchange), config={"displayModeBar": False}), width=3),
                dbc.Col([
                    html.H6("Execution Summary", style={"color": "#3b82f6", "textTransform": "uppercase", "letterSpacing": "0.1em", "fontSize": "12px", "marginBottom": "12px"}),
                    dbc.Table([
                        html.Thead(html.Tr([html.Th("Metric"), html.Th("Value")])),
                        html.Tbody([
                            html.Tr([html.Td(k), html.Td(str(v))])
                            for k, v in summary.items()
                        ]),
                    ], bordered=False, dark=True, hover=True, size="sm",
                       style={"fontSize": "13px"}),
                ], width=4),
                dbc.Col([
                    html.H6("Latency Percentiles", style={"color": "#3b82f6", "textTransform": "uppercase", "letterSpacing": "0.1em", "fontSize": "12px", "marginBottom": "12px"}),
                    dbc.Table([
                        html.Thead(html.Tr([html.Th("Percentile"), html.Th("Latency (µs)")])),
                        html.Tbody([
                            html.Tr([html.Td("P50"), html.Td(str(latency.get("p50_us", "N/A")))]),
                            html.Tr([html.Td("P75"), html.Td(str(latency.get("p75_us", "N/A")))]),
                            html.Tr([html.Td("P90"), html.Td(str(latency.get("p90_us", "N/A")))]),
                            html.Tr([html.Td("P95"), html.Td(str(latency.get("p95_us", "N/A")))]),
                            html.Tr([html.Td("P99"), html.Td(str(latency.get("p99_us", "N/A")))]),
                            html.Tr([html.Td("Max"), html.Td(str(latency.get("max_us", "N/A")))]),
                        ]),
                    ] if latency else [], bordered=False, dark=True, hover=True, size="sm",
                       style={"fontSize": "13px"}),
                ], width=5),
            ], className="g-3"),
        ], style={"padding": "0 32px", "marginBottom": "24px"}),

        # ---- Footer --------------------------------------------------------
        html.Div(
            "High-Performance Electronic Exchange Simulator © 2025",
            style={"textAlign": "center", "color": "#475569", "fontSize": "12px",
                   "padding": "16px", "borderTop": "1px solid #1e2a3a"},
        ),
    ], style={"background": "#0a0e1a", "minHeight": "100vh", "fontFamily": "Segoe UI, system-ui"})


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(exchange: Exchange | None = None) -> dash.Dash:
    """Create and configure the Dash application."""
    ex = exchange or EXCHANGE
    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        title="Electronic Exchange Simulator",
        suppress_callback_exceptions=True,
    )
    app.layout = build_layout(ex)
    return app


def run_server(debug: bool = False, port: int = 8050) -> None:
    """Launch the Dash development server."""
    app = create_app()
    app.run(debug=debug, port=port, host="0.0.0.0")


if __name__ == "__main__":
    print("🚀 Launching Exchange Dashboard at http://localhost:8050")
    run_server(debug=False)
