#!/usr/bin/env python3
"""Refresh the portfolio: fetch current prices, then build the HTML report.

This is the one script to run for a normal update. It runs, in order:
  1. src/linked_accounts.py fetch -> data/holdings_linked.csv
                                     (only if a login has been linked)
  2. src/fetch_prices.py  -> data/prices.csv, data/tips_prices.csv
  3. src/report.py        -> output/portfolio_report.html

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

    if (SRC.parent / "config" / "plaid_items.json").exists():
        if run("linked_accounts.py", "fetch") != 0:
            # failed logins drop out of the CSV; report.py uses the workbook
            # Holdings sheet for those accounts instead
            print("\nWARNING: some linked logins failed; their accounts use "
                  "the workbook Holdings sheet.", file=sys.stderr)

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
