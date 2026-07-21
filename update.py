#!/usr/bin/env python3
"""Refresh the portfolio: fetch current prices, then build the HTML report.

This is the one script to run for a normal update. It runs, in order:
  1. src/fetch_prices.py  -> data/prices.csv, data/tips_prices.csv
  2. src/report.py        -> output/portfolio_report.html

Usage:
  uv run update.py [--debug]

--debug is passed through to fetch_prices.py (saves raw HTTP responses).
"""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"


def run(script, *args):
    print(f"\n=== {script} ===", flush=True)
    return subprocess.run([sys.executable, str(SRC / script), *args]).returncode


def main():
    debug = ["--debug"] if "--debug" in sys.argv[1:] else []

    code = run("fetch_prices.py", *debug)
    if code != 0:
        # exit 1 means some quotes/CUSIPs came back incomplete; the report can
        # still be built from whatever was written, so warn and continue.
        print("\nWARNING: fetch_prices.py reported incomplete data "
              f"(exit {code}); building report anyway.", file=sys.stderr)

    code = run("report.py")
    if code != 0:
        sys.exit(code)


if __name__ == "__main__":
    main()
