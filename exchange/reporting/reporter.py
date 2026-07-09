"""
Report generation — JSON, CSV, HTML.

Produces three output formats from Exchange state:
  1. JSON report (machine-readable; for APIs and dashboards)
  2. CSV report  (tabular; for Excel/pandas analysis)
  3. HTML report (human-readable; for presentation)

HTML is generated via Jinja2 template rendering for clean separation
of presentation from logic.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from exchange.analytics.metrics import (
    compute_imbalance_from_depth,
    compute_mid_price,
    compute_spread,
    compute_vwap,
)
from exchange.core.exchange import Exchange


class ExchangeReporter:
    """
    Generates reports from Exchange state.

    Reports are written to the configured output directory.
    All formats contain the same underlying data; choose format by audience.
    """

    TEMPLATE_NAME = "report.html.j2"

    def __init__(
        self,
        exchange: Exchange,
        output_dir: str = "reports",
        template_dir: str = "templates",
    ) -> None:
        self._exchange = exchange
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Jinja2 environment
        template_path = Path(template_dir)
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(template_path)),
            autoescape=select_autoescape(["html"]),
        )
        self._jinja_env.filters["format_int"] = lambda v: f"{v:,}" if v is not None else "N/A"
        self._jinja_env.filters["format_float"] = (
            lambda v: f"{v:,.4f}" if v is not None else "N/A"
        )

    # -----------------------------------------------------------------------
    # Public report generation methods
    # -----------------------------------------------------------------------

    def generate_all(self) -> dict[str, str]:
        """
        Generate all three report formats.

        Returns a dict of format → output file path.
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        symbol = self._exchange.symbol

        json_path = self.generate_json(filename=f"{symbol}_report_{ts}.json")
        csv_path = self.generate_csv(filename=f"{symbol}_trades_{ts}.csv")
        html_path = self.generate_html(filename=f"{symbol}_report_{ts}.html")

        return {"json": json_path, "csv": csv_path, "html": html_path}

    def generate_json(self, filename: str | None = None) -> str:
        """Generate a JSON report. Returns the output file path."""
        data = self._build_report_data()
        filename = filename or f"{self._exchange.symbol}_report.json"
        path = self._output_dir / filename

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        return str(path)

    def generate_csv(self, filename: str | None = None) -> str:
        """Generate a CSV file of all trades. Returns the output file path."""
        trades = self._exchange.get_trades()
        filename = filename or f"{self._exchange.symbol}_trades.csv"
        path = self._output_dir / filename

        if not trades:
            # Write empty CSV with headers
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "trade_id", "symbol", "price", "quantity", "notional",
                    "buy_order_id", "sell_order_id",
                    "buyer_trader_id", "seller_trader_id", "executed_at",
                ])
            return str(path)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=trades[0].to_dict().keys())
            writer.writeheader()
            for trade in trades:
                writer.writerow(trade.to_dict())

        return str(path)

    def generate_html(self, filename: str | None = None) -> str:
        """
        Generate an HTML report using Jinja2 template.

        Returns the output file path.
        """
        data = self._build_report_data()
        filename = filename or f"{self._exchange.symbol}_report.html"
        path = self._output_dir / filename

        try:
            template = self._jinja_env.get_template(self.TEMPLATE_NAME)
            html = template.render(**data)
        except Exception:
            # Fallback: simple HTML without template
            html = self._build_fallback_html(data)

        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

        return str(path)

    def generate_execution_report_csv(self, filename: str | None = None) -> str:
        """Generate a CSV of all ExecutionReports."""
        reports = self._exchange.get_execution_history()
        filename = filename or f"{self._exchange.symbol}_exec_reports.csv"
        path = self._output_dir / filename

        if not reports:
            with open(path, "w", newline="") as f:
                f.write("exec_id,order_id,exec_type,order_status,filled_qty,timestamp\n")
            return str(path)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=reports[0].to_dict().keys())
            writer.writeheader()
            for r in reports:
                writer.writerow(r.to_dict())

        return str(path)

    # -----------------------------------------------------------------------
    # Data assembly
    # -----------------------------------------------------------------------

    def _build_report_data(self) -> dict[str, Any]:
        """Assemble all data needed by the templates and JSON report."""
        ex = self._exchange
        summary = ex.get_summary()
        trades = ex.get_trades()
        latency = ex.get_latency_stats()
        market_data = ex.get_market_data()

        # Market quality from latest snapshot
        best_bid = market_data.get("best_bid")
        best_ask = market_data.get("best_ask")
        market_quality = {
            "spread": compute_spread(best_bid, best_ask),
            "mid_price": compute_mid_price(best_bid, best_ask),
            "imbalance": compute_imbalance_from_depth(market_data),
            "best_bid": best_bid,
            "best_ask": best_ask,
        }

        return {
            "symbol": ex.symbol,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "summary": summary,
            "latency": latency if latency else None,
            "trades": trades[-50:],  # Last 50 trades for the HTML table
            "all_trades": trades,
            "market_quality": market_quality,
            "depth": market_data,
        }

    @staticmethod
    def _build_fallback_html(data: dict) -> str:
        """Simple fallback HTML if Jinja2 template fails."""
        summary = data.get("summary", {})
        return f"""<!DOCTYPE html>
<html>
<head><title>Exchange Report — {data['symbol']}</title>
<style>body{{font-family:sans-serif;background:#111;color:#eee;padding:2rem;}}
h1{{color:#3b82f6;}} table{{border-collapse:collapse;width:100%;}}
th,td{{border:1px solid #333;padding:8px;text-align:left;}}
th{{background:#222;}}</style></head>
<body>
<h1>Exchange Report — {data['symbol']}</h1>
<p>Generated: {data['generated_at']}</p>
<h2>Summary</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  {''.join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in summary.items())}
</table>
</body></html>"""
