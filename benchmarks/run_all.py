"""
Run all benchmarks and save results to reports/benchmarks/.

Usage:
    python benchmarks/run_all.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import benchmark_book
import benchmark_matching


def run_all() -> None:
    print("\n" + "=" * 60)
    print("  HIGH-PERFORMANCE ELECTRONIC EXCHANGE SIMULATOR")
    print("  Benchmark Suite")
    print("=" * 60)

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "book_benchmarks": benchmark_book.run(),
        "matching_benchmarks": benchmark_matching.run(),
    }

    # Save to JSON
    output_dir = Path("reports/benchmarks")
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"benchmark_results_{ts}.json"

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n[OK] Results saved to {output_path}")
    print("\nSummary:")
    for r in results["book_benchmarks"] + results["matching_benchmarks"]:
        if "ops_per_sec" in r:
            print(f"  {r['operation']}: {r['ops_per_sec']:,} ops/sec")


if __name__ == "__main__":
    run_all()
