#!/usr/bin/env python3
"""Fill the Assets sheet with each fund's actual asset-class split.

Reads each fund's latest SEC N-PORT filing (N-MFP for money market funds),
following funds of funds through to the underlying funds, and sums the
holdings into the Classes of the Targets sheet. An unlisted fund uses a
comparable fund ("like TICKER" in Source). "manual" rows are never looked up.
The Source values are listed in README.md (Fund look-through); what this
reads and writes is in docs/ARCHITECTURE.md.

Usage:
  uv run fetch-composition [--dry-run] [TICKER ...]
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from functools import cache
from pathlib import Path

from workbook_io import WORKBOOK, backup, ensure_closed, require_workbook

ROOT = Path(__file__).resolve().parent.parent
CONTACT = ROOT / "config" / "sec_contact.txt"
CACHE = ROOT / "data" / "nport"
SEC = "https://www.sec.gov"
NS = "{http://www.sec.gov/edgar/nport}"

# classes this program can fill in, in the order rows are written
AUTO = ["U.S. Total Mkt", "Intl Total Mkt", "Emerging Mkt",
        "U.S. Bonds", "TIPS", "Intl Bonds", "Cash"]
# FTSE emerging + frontier markets, plus HK (see docstring)
EMERGING = set("AE BR CL CN CO CZ EG GR HK HU ID IN IS KE KW MX MY NG PE PH "
               "PK QA RO SA TH TR TW ZA".split())
DERIVATIVES = {"DE", "DIR", "DFE", "DCR", "DCO", "DO"}   # pctVal is only P&L
MAX_DEPTH = 3


# ---------------------------------------------------------------- SEC access
@cache
def user_agent():
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua and CONTACT.exists():
        ua = CONTACT.read_text().strip()
    if not ua:
        if not sys.stdin.isatty():
            sys.exit(f"No SEC contact. Set SEC_USER_AGENT or write {CONTACT}.")
        print("The SEC asks every program that downloads its filings to send "
              "a name and contact email\n(e.g. 'Jane Doe jane@example.org'). "
              f"It is saved in {CONTACT.relative_to(ROOT)}.")
        ua = input("Name and email: ").strip()
        if "@" not in ua:
            sys.exit("Expected a name and an email address.")
        CONTACT.parent.mkdir(exist_ok=True)
        CONTACT.write_text(ua + "\n")
    return ua


def get(url, tries=3):
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            time.sleep(0.15)          # SEC fair-access limit is 10 requests/s
            return body
        except Exception as e:
            if attempt == tries:
                raise
            print(f"  retry {attempt}/{tries - 1} after error: {e}")
            time.sleep(2 * attempt)


def cached(name, url, max_age_days):
    """Download url to data/nport/name unless a fresh enough copy exists."""
    path = CACHE / name
    if not path.exists() or time.time() - path.stat().st_mtime > max_age_days * 86400:
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(get(url))
    return path


@cache
def directory():
    """ticker -> series id, series name (lower case) -> series id, id -> name."""
    mf = json.loads(cached("company_tickers_mf.json",
                           f"{SEC}/files/company_tickers_mf.json", 30).read_text())
    by_ticker = {r[3].upper(): r[1] for r in mf["data"]}
    base = f"{SEC}/files/investment/data/other/investment-company-series-class-information"
    for year in (date.today().year, date.today().year - 1):
        try:
            path = cached(f"series_class_{year}.csv",
                          f"{base}/investment-company-series-class-{year}.csv", 30)
            break
        except Exception:     # the new year's file appears some weeks in
            continue
    else:
        sys.exit("Could not download the SEC series/class list.")
    by_name, names = {}, {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            by_name.setdefault(r["Series Name"].strip().lower(), r["Series ID"])
            names[r["Series ID"]] = r["Series Name"].strip()
    return by_ticker, by_name, names


def newest_filing(series, form):
    """(index URL, filing date) of the series' newest filing of `form`."""
    # EDGAR sometimes returns no entries for count < 10
    atom = get(f"{SEC}/cgi-bin/browse-edgar?action=getcompany&CIK={series}"
               f"&type={form}&dateb=&owner=include&count=10&output=atom"
               ).decode("utf-8", "replace")
    for entry in re.findall(r"<entry>(.*?)</entry>", atom, re.S):
        kind = re.search(r"<filing-type>([^<]*)", entry)
        href = re.search(r"<filing-href>([^<]*)", entry)
        when = re.search(r"<filing-date>([^<]*)", entry)
        if kind and href and kind.group(1).startswith(form):
            return href.group(1), when.group(1) if when else ""
    return None


def latest_filing(series):
    """Path of the series' most recent N-PORT filing, downloaded if new."""
    found = newest_filing(series, "NPORT-P")
    if found is None:
        return None
    folder = found[0].rsplit("/", 1)[0]
    acc = folder.rsplit("/", 1)[1]
    path = CACHE / f"{series}_{acc}.xml"
    if not path.exists():
        print(f"  downloading {series} filing {acc}")
        body = get(f"{folder}/primary_doc.xml")
        if not body.lstrip().startswith(b"<?xml"):
            raise RuntimeError(f"{folder}/primary_doc.xml is not an N-PORT XML file")
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        for old in CACHE.glob(f"{series}_*.xml"):     # keep only the latest
            if old != path:
                old.unlink()
    return path


# ---------------------------------------------------------------- look-through
def classify(f):
    cat, issuer, country = f["assetCat"], f["issuerCat"], f["invCountry"]
    text = f"{f['title']} {f['name']}".upper()
    if cat == "STIV" or "MARKET LIQUIDITY" in text:
        return "Cash"
    if cat in ("EC", "EP"):
        if country == "US":
            return "U.S. Total Mkt"
        return "Emerging Mkt" if country in EMERGING else "Intl Total Mkt"
    if cat in ("DBT", "SN", "LON") or cat.startswith("ABS"):
        if issuer == "UST" and re.search(r"TIPS|INFL|\bTII\b", text):
            return "TIPS"
        return "U.S. Bonds" if country == "US" else "Intl Bonds"
    if cat in DERIVATIVES:
        return None
    return "Other"


def holdings(path):
    """Yield (fields, pct of net assets) for each holding; also the as-of date."""
    keep = ("name", "title", "assetCat", "issuerCat", "invCountry", "pctVal")
    asof = None
    for _, el in ET.iterparse(path):
        if el.tag == NS + "repPdDate":
            asof = el.text
        elif el.tag == NS + "invstOrSec":
            f = {k: (el.findtext(NS + k) or "").strip() for k in keep}
            # derivatives and ADRs carry their category on an attribute instead
            cond = el.find(NS + "assetConditional")
            if not f["assetCat"] and cond is not None:
                f["assetCat"] = cond.get("assetCat", "")
                if re.search(r"\b[AG]DRS?\b|DEPOSITARY", cond.get("desc", "").upper()):
                    f["assetCat"] = "EC"
            yield f, float(f["pctVal"] or 0) / 100, asof
            el.clear()


@cache
def look_through(series, depth=0):
    """({class: weight} summing to 1, as-of date, notes), or None if no filing."""
    path = latest_filing(series)
    if path is None:
        return None
    _, by_name, _ = directory()
    w, notes, asof = {}, [], None
    for f, pct, asof in holdings(path):
        sub = by_name.get(f["name"].lower())
        if sub and sub != series and "liquidity" not in f["name"].lower() \
                and depth < MAX_DEPTH:
            inner = look_through(sub, depth + 1)
            if inner:
                notes.append(f"{pct:.1%} in {f['name']}")
                for cls, v in inner[0].items():
                    w[cls] = w.get(cls, 0) + v * pct
                continue
        cls = classify(f)
        if cls is None:
            continue
        if cls == "U.S. Total Mkt" and pct > 0.01 and re.search(
                r"\b(FUND|ETF|TRUST)\b", f["name"].upper()):
            notes.append(f"WARNING: {pct:.1%} in {f['name']} counted as a "
                         "U.S. stock; it may be a fund this program could not find")
        w[cls] = w.get(cls, 0) + pct
    # more than 100% is mostly securities-lending collateral the fund owes back
    excess = sum(w.values()) - 1
    if excess > 0:
        w["Cash"] = max(0.0, w.get("Cash", 0) - excess)
    other = w.pop("Other", 0)
    if other > 0.005:
        notes.append(f"WARNING: {other:.1%} in holdings of no known class left out")
    total = sum(w.values())
    if total <= 0:
        return None
    return {k: v / total for k, v in w.items()}, asof, notes


def rounded(weights):
    """Round to 4 places, drop slices under 0.05%, make the total exactly 1."""
    out = {c: round(weights[c], 4) for c in AUTO if weights.get(c, 0) >= 0.0005}
    big = max(out, key=out.get)
    out[big] = round(out[big] + 1 - sum(out.values()), 4)
    return out


# ---------------------------------------------------------------- workbook
def update_assets(path, only, dry_run):
    import openpyxl
    from copy import copy

    require_workbook(path)
    if not dry_run:
        ensure_closed(path, "fetch-composition")
    wb = openpyxl.load_workbook(path)
    ws = wb["Assets"]
    old = [list(r) + [None] * (6 - len(r))
           for r in ws.iter_rows(min_row=2, max_col=6, values_only=True)
           if any(v not in (None, "") for v in r)]
    tickers = list(dict.fromkeys(r[0] for r in old))
    held = [r[1] for r in wb["Holdings"].iter_rows(min_row=2, values_only=True)
            if r and r[1]]
    tickers += [t for t in dict.fromkeys(held) if t not in tickers]
    if only:
        tickers = [t for t in tickers if t.upper() in only]

    by_ticker, _, names = directory()
    new, failed = {}, False
    for t in tickers:
        rows = [r for r in old if r[0] == t]
        sources = {str(r[5] or "").lower() for r in rows}
        if "manual" in sources:
            print(f"  {t}: marked manual; left as is")
            continue
        like = next((m.group(1) for s in sources
                     if (m := re.match(r"like ([^\s,]+)", s))), None)
        unknown = sorted({r[2] for r in rows} - set(AUTO) - {None})
        if unknown and not any(s.startswith(("n-port", "n-mfp")) for s in sources):
            for r in rows:
                r[5] = "manual"
            print(f"  {t}: uses {', '.join(map(str, unknown))}, which filings "
                  "can't determine; marked manual")
            continue
        if str(t).upper() == "CASH":
            if not rows:
                new[t] = [[t, "Uninvested cash", "Cash", 1, 1, "manual"]]
                print(f"  {t}: added as Cash, price override 1")
            continue
        series = by_ticker.get((like or str(t)).upper())
        if not series:
            if like:
                print(f"  {t}: {like.upper()} is not an SEC-registered fund; "
                      "left as is")
            elif rows:
                print(f"  {t}: not an SEC-registered fund; left as is"
                      + ("" if rows[0][2] else " (Class still blank)"))
            else:
                new[t] = [[t, t, None, None, None, None]]
                print(f"  {t}: not an SEC-registered fund; added with no "
                      "Class. Fill in Class and Class Pct, or set Source "
                      "to 'like TICKER'")
            continue
        try:
            res = look_through(series)
        except Exception as e:
            print(f"  {t}: ERROR {e}; left as is")
            failed = True
            continue
        if res is None:
            mmf = newest_filing(series, "N-MFP")
            if mmf is None:
                print(f"  {t}: no N-PORT or N-MFP filing; left as is")
                continue
            res = {"Cash": 1.0}, mmf[1], ["money market fund"]
            kind = "N-MFP"
        else:
            kind = "N-PORT"
        weights, asof, notes = res
        weights = rounded(weights)
        name = ((rows[0][1] if rows else None)
                or (t if like else names.get(series, t)))
        override = next((r[4] for r in rows if r[4] is not None), None)
        source = (f"like {like.upper()}, " if like else "") + f"{kind} {asof}"
        new[t] = [[t, name, c, p, override if i == 0 else None, source]
                  for i, (c, p) in enumerate(weights.items())]
        before = {r[2]: r[3] for r in rows}
        changes = [f"{c} {before.get(c) or 0:g} -> {weights.get(c, 0):g}"
                   for c in AUTO + sorted(set(before) - set(AUTO))
                   if round(before.get(c) or 0, 4) != weights.get(c, 0)]
        print(f"  {t} ({source}): "
              + ("; ".join(changes) if changes else "no change"))
        for n in notes:
            print(f"      {n}")

    out, placed = [], set()
    for r in old:
        if r[0] in new:
            if r[0] not in placed:
                out.extend(new[r[0]])
                placed.add(r[0])
        else:
            out.append(r)
    for t in new:                       # tickers held but not yet on Assets
        if t not in placed:
            out.extend(new[t])

    if dry_run:
        print("Dry run: workbook not changed.")
        return 1 if failed else 0
    saved = backup(path)
    cell = ws.cell(row=1, column=6, value="Source")
    cell._style = copy(ws.cell(row=1, column=1)._style)
    ws.column_dimensions["F"].width = 28
    ws.delete_rows(2, ws.max_row)
    for r in out:
        ws.append(r)
    wb.save(path)
    print(f"Updated Assets sheet in {path} (backup: {saved})")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tickers", nargs="*", help="only these tickers")
    ap.add_argument("--workbook", default=WORKBOOK)
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would change without saving")
    args = ap.parse_args()
    sys.exit(update_assets(Path(args.workbook), {t.upper() for t in args.tickers},
                           args.dry_run))


if __name__ == "__main__":
    main()
