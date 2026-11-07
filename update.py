#!/usr/bin/env python3
"""Refresh the portfolio: fetch holdings and prices, then build the report.

Runs `linked-accounts fetch` (only if a login is linked), then
`fetch-prices`, then `report`. See docs/ARCHITECTURE.md.

Usage:
  uv run update.py [--debug]    # --debug is passed through to fetch-prices
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
            # a failed login's Holdings rows are left as they were
            print("\nWARNING: some linked logins failed; their Holdings rows "
                  "were not refreshed.", file=sys.stderr)

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
