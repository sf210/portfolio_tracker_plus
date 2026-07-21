#!/usr/bin/env python3
"""One-time builder: extract input data from the Bogleheads Portfolio Tracker
xlsx and write a lean, data-only workbook (portfolio_input.xlsx) that is
edited in LibreOffice Calc and read by report.py.

Sheets written:
  Accounts  - Name, Type, Institution, Owner, Tax Type
  Holdings  - Account, Ticker, Shares
  TIPS      - Account, CUSIP, Face, Coupon, Maturity, Description
  Assets    - Ticker, Name, Class, Class Pct, Price Override
  Targets   - Class, Category, Parent, Target, Threshold

Usage:
  ~/finance/planning/.venv/bin/python src/build_input_workbook.py [--force]
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "src" / "Portfolio Tracker v2.1.1.xlsx"
TIPS_STMT = ROOT / "data" / "tips_stmt.txt"
OUTPUT = ROOT / "src" / "portfolio_input.xlsx"

# Placeholder ticker for the TIPS ladder in the tracker; replaced by the
# CUSIP-level TIPS sheet, so it is dropped from Holdings and Assets.
TIPS_PLACEHOLDER = "VTP"

# Money-market funds quote at a fixed $1.00; no fetch needed.
FIXED_PRICE = {"VMFXX": 1.0, "SPAXX": 1.0}


def parse_tips_statement(path):
    """Parse coupon/maturity per CUSIP from the Vanguard statement text.

    Statement blocks look like:
      91282CBF7 U S TREASURY NOTE ... 10,000.0000 ...
                INFLATION INDEX NOTE CPN 0.125% DUE 01/15/31
    """
    text = path.read_text()
    info = {}
    cusip = None
    for line in text.splitlines():
        m = re.match(r"^(\w{9})\s+U S TREASURY", line)
        if m:
            cusip = m.group(1)
            qty = re.search(r"([\d,]+\.\d{4})", line)
            face = float(qty.group(1).replace(",", "")) if qty else None
            info[cusip] = {"face": face}
            continue
        m = re.search(r"CPN\s+([\d.]+)%\s+DUE\s+(\d{2}/\d{2}/\d{2})", line)
        if m and cusip:
            info[cusip]["coupon"] = float(m.group(1))
            mm, dd, yy = m.group(2).split("/")
            info[cusip]["maturity"] = datetime(2000 + int(yy), int(mm), int(dd)).date()
            cusip = None
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite existing output")
    args = ap.parse_args()

    if OUTPUT.exists() and not args.force:
        sys.exit(f"{OUTPUT} already exists (it may contain your edits). "
                 "Use --force to overwrite.")

    src = openpyxl.load_workbook(TRACKER, data_only=True)
    tips_meta = parse_tips_statement(TIPS_STMT) if TIPS_STMT.exists() else {}

    out = openpyxl.Workbook()
    bold = Font(bold=True)

    def new_sheet(title, headers, first=False):
        ws = out.active if first else out.create_sheet()
        ws.title = title
        ws.append(headers)
        for c in ws[1]:
            c.font = bold
        return ws

    # ---- Accounts -----------------------------------------------------
    acct_src = src["Account Setup"]
    tax_map = {}          # account type -> tax type (cols J/K)
    for r in range(4, acct_src.max_row + 1):
        t, tax = acct_src.cell(r, 10).value, acct_src.cell(r, 11).value
        if t:
            tax_map[t] = tax
    ws = new_sheet("Accounts", ["Name", "Type", "Institution", "Owner", "Tax Type"],
                   first=True)
    accounts = []
    for r in range(4, acct_src.max_row + 1):
        name = acct_src.cell(r, 2).value
        if not name:
            continue
        typ = acct_src.cell(r, 3).value
        ws.append([name, typ, acct_src.cell(r, 4).value,
                   acct_src.cell(r, 5).value, tax_map.get(typ, "")])
        accounts.append(name)

    # ---- Holdings -----------------------------------------------------
    hold_src = src["Holdings"]
    ws = new_sheet("Holdings", ["Account", "Ticker", "Shares"])
    n_hold = 0
    for r in range(4, hold_src.max_row + 1):
        acct = hold_src.cell(r, 2).value
        tick = hold_src.cell(r, 7).value
        shares = hold_src.cell(r, 11).value
        if not acct or not tick or tick == TIPS_PLACEHOLDER:
            continue
        ws.append([acct, tick, shares])
        n_hold += 1

    # ---- TIPS ---------------------------------------------------------
    tips_src = src["TIPS Holdings"]
    ws = new_sheet("TIPS", ["Account", "CUSIP", "Face", "Coupon",
                            "Maturity", "Description"])
    n_tips = 0
    for r in range(2, tips_src.max_row + 1):
        cusip = tips_src.cell(r, 1).value
        if not cusip:
            continue
        face = tips_src.cell(r, 2).value
        desc = tips_src.cell(r, 3).value
        meta = tips_meta.get(cusip, {})
        if meta.get("face") is not None and meta["face"] != face:
            print(f"WARNING: {cusip} face {face} in tracker but "
                  f"{meta['face']} on statement")
        ws.append(["vg ira", cusip, face, meta.get("coupon"),
                   meta.get("maturity"), desc])
        n_tips += 1
    for cusip in tips_meta:
        listed = {tips_src.cell(r, 1).value for r in range(2, tips_src.max_row + 1)}
        if cusip not in listed:
            print(f"WARNING: {cusip} on statement but not in tracker TIPS sheet")

    # ---- Assets -------------------------------------------------------
    asset_src = src["Asset Setup"]
    ws = new_sheet("Assets", ["Ticker", "Name", "Class", "Class Pct",
                              "Price Override"])
    n_assets = 0
    for r in range(4, asset_src.max_row + 1):
        tick = asset_src.cell(r, 2).value
        if not tick or tick == TIPS_PLACEHOLDER:
            continue
        pct = asset_src.cell(r, 5).value
        ws.append([tick, asset_src.cell(r, 3).value, asset_src.cell(r, 4).value,
                   pct if pct is not None else 1.0, FIXED_PRICE.get(tick)])
        n_assets += 1

    # ---- Targets ------------------------------------------------------
    alloc_src = src["Allocation"]
    ws = new_sheet("Targets", ["Class", "Category", "Parent", "Target",
                               "Threshold"])
    n_tgt = 0
    for r in range(4, 40):
        cls = alloc_src.cell(r, 2).value
        if not cls:
            continue
        ws.append([cls, alloc_src.cell(r, 4).value, alloc_src.cell(r, 5).value,
                   alloc_src.cell(r, 6).value or 0, alloc_src.cell(r, 10).value or 0])
        n_tgt += 1

    for ws in out.worksheets:
        for col in ws.columns:
            width = max(len(str(c.value)) for c in col if c.value is not None)
            ws.column_dimensions[col[0].column_letter].width = min(width + 2, 45)

    out.save(OUTPUT)
    print(f"Wrote {OUTPUT}")
    print(f"  Accounts: {len(accounts)}, Holdings: {n_hold} (dropped "
          f"{TIPS_PLACEHOLDER} placeholder), TIPS: {n_tips}, "
          f"Assets: {n_assets}, Targets: {n_tgt}")


if __name__ == "__main__":
    main()
