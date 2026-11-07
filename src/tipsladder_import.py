#!/usr/bin/env python3
"""Import a tipsladder.com ladder into the workbook's TIPS sheet.

Reads the CSV that tipsladder.com exports (CUSIP, Bond count, Years funded,
Maturity date, Net purchase cost) and replaces one Account's rows on the
TIPS sheet with it. Face is bond count x $1,000, Cost Basis is the net
purchase cost, Years Funded is copied, and the coupon is looked up by CUSIP
from TreasuryDirect.
Other Accounts' TIPS rows are left alone.

Usage:
  uv run import-tipsladder LADDER.csv --account IRA [--dry-run]
  uv run import-tipsladder LADDER.csv --account IRA \\
      --workbook examples/portfolio_input.example.xlsx
"""

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

import openpyxl

from fetch_prices import get
from workbook_io import WORKBOOK, backup, ensure_closed, require_workbook

HEADERS = ["Account", "CUSIP", "Face", "Coupon", "Maturity", "Description",
           "Cost Basis", "Years Funded"]
TD_SEARCH = "https://www.treasurydirect.gov/TA_WS/securities/search?cusip={}&format=json"


def read_ladder(path):
    """[(cusip, face, maturity, cost, years funded)] from a tipsladder.com CSV."""
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            cusip = (r.get("CUSIP") or "").strip()
            if not cusip:
                continue
            count = int(r["Bond count"])
            maturity = date.fromisoformat(r["Maturity date"].strip())
            cost = float(r["Net purchase cost"].replace("$", "")
                         .replace(",", "").strip())
            funded = " ".join((r.get("Years funded") or "").split())
            out.append((cusip, count * 1000, maturity, cost, funded or None))
    return out


def lookup_coupon(cusip, maturity):
    """Coupon in percent from TreasuryDirect; None if the lookup fails."""
    try:
        recs = json.loads(get(TD_SEARCH.format(cusip)))
    except Exception as e:
        print(f"  {cusip}: TreasuryDirect lookup failed: {e}")
        return None
    recs = [r for r in recs if r.get("interestRate")]
    if not recs:
        print(f"  {cusip}: TreasuryDirect has no coupon for it")
        return None
    r = recs[0]
    if r.get("type") != "TIPS":
        print(f"  WARNING: {cusip} is a {r.get('type')}, not a TIPS")
    td_mat = (r.get("maturityDate") or "")[:10]
    if td_mat and td_mat != maturity.isoformat():
        print(f"  WARNING: {cusip} matures {td_mat} at TreasuryDirect, "
              f"{maturity} in the ladder")
    return float(r["interestRate"])


def main():
    ap = argparse.ArgumentParser(
        description="Replace an Account's TIPS rows with a tipsladder.com ladder.")
    ap.add_argument("ladder", type=Path, help="tipsladder.com CSV export")
    ap.add_argument("--account", required=True,
                    help="Accounts-sheet Name that holds the ladder")
    ap.add_argument("--workbook", type=Path, default=WORKBOOK,
                    help="workbook to update (default: data/portfolio_input.xlsx)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the rows without writing")
    args = ap.parse_args()

    require_workbook(args.workbook)
    ladder = read_ladder(args.ladder)
    if not ladder:
        sys.exit(f"No bonds found in {args.ladder}")

    wb = openpyxl.load_workbook(args.workbook)
    accounts = {r[0] for r in wb["Accounts"].iter_rows(min_row=2, values_only=True)
                if r and r[0]}
    if args.account not in accounts:
        sys.exit(f"{args.account!r} is not a Name on the Accounts sheet "
                 f"({', '.join(sorted(accounts))})")

    print(f"Looking up {len(ladder)} coupons at TreasuryDirect...")
    rows = []
    for cusip, face, maturity, cost, funded in ladder:
        coupon = lookup_coupon(cusip, maturity)
        rows.append([args.account, cusip, face, coupon, maturity,
                     f"TIPS {maturity:%b-%Y}", round(cost, 2), funded])

    ws = wb["TIPS"]
    old = [list(r) for r in ws.iter_rows(min_row=2, max_col=8, values_only=True)
           if any(v is not None for v in r)]
    kept = [r for r in old if r[0] != args.account]
    replaced = len(old) - len(kept)

    for r in rows:
        c = "?" if r[3] is None else f"{r[3]:g}%"
        print(f"  {r[1]}  {r[5]:<13} face {r[2]:>7,}  coupon {c:<7} "
              f"cost {r[6]:>10,.2f}  funds {r[7] or ''}")
    print(f"{args.account}: {replaced} TIPS rows -> {len(rows)}; "
          f"face {sum(r[2] for r in rows):,}, "
          f"cost {sum(r[6] for r in rows):,.2f}")
    missing = [r[1] for r in rows if r[3] is None]
    if missing:
        print(f"WARNING: no coupon for {', '.join(missing)}; fill in Coupon by hand")
    if args.dry_run:
        print("Dry run: nothing written.")
        return

    ensure_closed(args.workbook, "import-tipsladder")
    print(f"Backed up to {backup(args.workbook)}")
    ws.delete_rows(2, ws.max_row)
    for c, h in enumerate(HEADERS, 1):
        if ws.cell(1, c).value is None:
            ws.cell(1, c, h)
    for i, r in enumerate(kept + rows, start=2):
        for c, v in enumerate(r, 1):
            ws.cell(i, c, v)
        ws.cell(i, 5).number_format = "yyyy-mm-dd"
    wb.save(args.workbook)
    print(f"Wrote {args.workbook}")


if __name__ == "__main__":
    main()
