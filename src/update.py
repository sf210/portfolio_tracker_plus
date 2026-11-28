"""Refresh the portfolio: fetch holdings and prices, then build the report.

Runs `linked-accounts fetch` (only if a login is linked), then
`fetch-prices`, then `report`. See docs/ARCHITECTURE.md.

Usage:
  uv run update [--debug]    # --debug is passed through to fetch-prices
  uv run update --workbook examples/portfolio_input.example.xlsx
      # another workbook: no Plaid fetch; its prices and report are kept
      # apart from the real ones (workbook_io.outputs_for)
"""
import argparse
import subprocess
import sys
from pathlib import Path

from workbook_io import WORKBOOK

SRC = Path(__file__).resolve().parent


def run(script, *args):
    print(f"\n=== {script} ===", flush=True)
    return subprocess.run([sys.executable, str(SRC / script), *args]).returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workbook", type=Path, default=WORKBOOK,
                    help="workbook to refresh (default: data/portfolio_input.xlsx)")
    ap.add_argument("--debug", action="store_true",
                    help="save fetch-prices' raw HTTP responses to data/")
    args = ap.parse_args()
    real = args.workbook.resolve() == WORKBOOK
    wb = [] if real else ["--workbook", str(args.workbook.resolve())]

    if not real:
        print(f"Workbook {args.workbook}: skipping linked-accounts fetch "
              "(Plaid only refreshes the real workbook).")
    elif (SRC.parent / "config" / "plaid_items.json").exists():
        if run("linked_accounts.py", "fetch") != 0:
            # a failed login's Holdings rows are left as they were
            print("\nWARNING: some linked logins failed; their Holdings rows "
                  "were not refreshed.", file=sys.stderr)

    code = run("fetch_prices.py", *wb, *(["--debug"] if args.debug else []))
    if code != 0:
        # exit 1 means some quotes/CUSIPs came back incomplete; the report can
        # still be built from whatever was written, so warn and continue.
        print("\nWARNING: fetch_prices.py reported incomplete data "
              f"(exit {code}); building report anyway.", file=sys.stderr)

    code = run("report.py", *wb)
    if code != 0:
        sys.exit(code)


if __name__ == "__main__":
    main()
