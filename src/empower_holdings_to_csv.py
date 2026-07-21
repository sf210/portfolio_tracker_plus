#!/usr/bin/env python3
"""Parse an Empower (Personal Dashboard / 401k) holdings PDF into a CSV.

Empower's Holdings view has no export button, so this works off a PDF print of
the page.  The PDF is converted to text with `pdftotext` (poppler); the text has
one value per line, with page headers/footers/timestamps interleaved.

Layout (after the first standalone "Fund" section line, everything before is UI
chrome):

    Holdings are printed in blocks.  A holding WITH a ticker is 7 lines:
        ticker
        name
        shares
        price
        change            (ignored)
        1-day change      (ignored)
        value
    A holding WITHOUT a ticker (e.g. bonds) drops the first line -> 6 lines.

    Section headings (Fund, ETF, Bond, Cash, Stock, Other) appear as a lone
    line before the first holding of a section and are dropped -- EXCEPT when
    such a word is actually a holding's name (it is then the block's only
    header line, immediately followed by the numbers).

Output columns: ticker, name, value, shares, price
(ticker is "NA" when the holding has none.)

Usage:
    empower_holdings_to_csv.py [input.pdf|input.txt] [-o holdings_empower.csv]
"""

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

# Section headings to strip.  Case-sensitive, exactly as Empower renders them.
SECTIONS = {"Fund", "ETF", "Bond", "Cash", "Stock", "Other"}

# The first standalone line equal to this marks the start of real data.
START_MARKER = "Fund"

# Everything at/after this trailing summary line is ignored.
STOP_MARKER = "Grand Total"

# A line is "financial" (a number) if it is a bare number (shares) or a dollar
# amount (price / change / value).  Everything else is treated as text.
RE_BARE_NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
RE_MONEY = re.compile(r"^[+-]?\$[\d,]+(?:\.\d+)?$")

# Recurring page noise to drop.
RE_PAGENUM = re.compile(r"^\d+ of \d+$")
RE_TIMESTAMP = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}$")
NOISE_EXACT = {"Employer 401(k) Participant Login"}


def is_financial(line):
    return bool(RE_BARE_NUM.match(line) or RE_MONEY.match(line))


def is_noise(line):
    return (
        line == ""
        or line in NOISE_EXACT
        or line.startswith("https://")
        or bool(RE_PAGENUM.match(line))
        or bool(RE_TIMESTAMP.match(line))
    )


def to_number(token):
    """Strip $ and thousands separators; return a plain numeric string + float."""
    cleaned = token.replace("$", "").replace(",", "")
    return cleaned, float(cleaned)


def load_text(path):
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        try:
            out = subprocess.run(
                ["pdftotext", str(path), "-"],
                check=True, capture_output=True, text=True,
            )
        except FileNotFoundError:
            sys.exit("error: pdftotext not found on PATH (install poppler).")
        except subprocess.CalledProcessError as e:
            sys.exit(f"error: pdftotext failed: {e.stderr}")
        return out.stdout.splitlines()
    return path.read_text().splitlines()


def parse(lines):
    """Yield holding dicts from the raw text lines."""
    # Skip everything up to and including the first standalone START_MARKER.
    started = False
    data = []
    for line in lines:
        s = line.strip()
        if not started:
            if s == START_MARKER:
                started = True
            continue
        if s == STOP_MARKER:
            break
        if is_noise(s):
            continue
        data.append(s)

    header = []      # accumulated text lines for the current holding
    fins = []        # accumulated financial values (as float) for current holding
    fin_raw = []     # matching cleaned numeric strings

    for s in data:
        if is_financial(s):
            raw, val = to_number(s)
            fins.append(val)
            fin_raw.append(raw)
            if len(fins) == 5:
                yield build_holding(header, fin_raw)
                header, fins, fin_raw = [], [], []
        else:
            if fins:
                # A text line mid-block means the block structure broke.
                raise ValueError(
                    f"unexpected text line {s!r} after {len(fins)} numeric "
                    f"line(s); block structure not as expected"
                )
            header.append(s)


def build_holding(header, fin_raw):
    """header: text lines (1-3); fin_raw: [shares, price, change, 1day, value]."""
    # Drop a leading section heading only when it isn't the block's sole header.
    if len(header) >= 2 and header[0] in SECTIONS:
        header = header[1:]

    if len(header) == 2:
        ticker, name = header[0], header[1]
    elif len(header) == 1:
        ticker, name = "NA", header[0]
    else:
        raise ValueError(f"cannot interpret header block: {header!r}")

    shares, price, _change, _oneday, value = fin_raw
    return {
        "ticker": ticker,
        "name": name,
        "value": value,
        "shares": shares,
        "price": price,
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input", nargs="?", default="holding0706.pdf",
                    help="input PDF or pre-converted .txt (default: holding0706.pdf)")
    ap.add_argument("-o", "--output", default="holdings_empower.csv",
                    help="output CSV path (default: holdings_empower.csv)")
    args = ap.parse_args()

    holdings = list(parse(load_text(args.input)))

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "name", "value", "shares", "price"])
        w.writeheader()
        w.writerows(holdings)

    total = sum(float(h["value"]) for h in holdings)
    print(f"Parsed {len(holdings)} holdings -> {args.output}")
    print(f"Total value: ${total:,.2f}")
    # Flag any non-standard ticker (mixed case / underscores) worth eyeballing.
    for h in holdings:
        if h["ticker"] != "NA" and not re.fullmatch(r"[A-Z0-9]+", h["ticker"]):
            print(f"  note: unusual ticker {h['ticker']!r} for {h['name']!r}")


if __name__ == "__main__":
    main()
