#!/usr/bin/env python3
"""Fetch current prices for the portfolio tracker.

Gets Quotes for listed tickers from Yahoo Finance, and TIPS clean prices
with index ratios from FedInvest, TreasuryDirect and BLS/FRED, and writes
them to data/. Unlisted funds are skipped; the report prices them from
Broker Price. Sources, outputs and price precedence are described in
docs/ARCHITECTURE.md.

Usage:
  uv run fetch-prices [--debug]    # --debug saves raw HTTP responses to data/
"""

import argparse
import csv
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl

from workbook_io import WORKBOOK, require_workbook

ROOT = Path(__file__).resolve().parent.parent
INPUT_WB = WORKBOOK
DATA = ROOT / "data"
PRICES_CSV = DATA / "prices.csv"
TIPS_CSV = DATA / "tips_prices.csv"
REF_CSV = DATA / "tips_ref.csv"     # cusip -> refCpiOnDatedDate cache

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) portfolio-tracker/1.0"}
DEBUG = False


def get(url, data=None, tries=3, timeout=60, headers=None):
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, data=data,
                                     headers={**UA, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", errors="replace")
            break
        except Exception as e:
            if attempt == tries:
                raise
            print(f"  retry {attempt}/{tries - 1} after error: {e}")
    if DEBUG:
        fn = DATA / ("debug_" + re.sub(r"\W+", "_", url)[-60:] + ".txt")
        fn.write_text(body)
        print(f"  [debug] {url} -> {fn.name} ({len(body)} bytes)")
    return body


def read_inputs():
    require_workbook(INPUT_WB)
    wb = openpyxl.load_workbook(INPUT_WB, data_only=True)
    tickers = []
    for row in wb["Assets"].iter_rows(min_row=2, values_only=True):
        ticker, _, _, _, override = row[:5]
        if ticker and override is None and ticker not in tickers:
            tickers.append(ticker)
    # unlisted funds (Holdings Price Source "broker") have no market quote;
    # report.py prices them from the Holdings Broker Price
    sources = {}
    for row in wb["Holdings"].iter_rows(min_row=2, max_col=7, values_only=True):
        if row and row[1]:
            src = str(row[5]).strip().lower() if len(row) > 5 and row[5] else ""
            sources.setdefault(row[1], set()).add(src)
    broker = [t for t in tickers if sources.get(t) == {"broker"}]
    for t in broker:
        print(f"  {t}: unlisted; priced from Broker Price")
    # fallback for unmarked rows: names such as "The Vanguard Target Retire
    # 2070 Trust I" aren't quotable either
    skipped = [t for t in tickers if t not in broker
               and not re.fullmatch(r"[\w.^=-]+", str(t))]
    for t in skipped:
        print(f"  {t}: not a market ticker; priced from Holdings Broker Price")
    tickers = [t for t in tickers if t not in broker and t not in skipped]
    tips = []   # (cusip, maturity)
    for row in wb["TIPS"].iter_rows(min_row=2, values_only=True):
        _, cusip, _, _, maturity, _ = row[:6]
        if cusip:
            tips.append((cusip, maturity))
    return tickers, tips


# ---------------------------------------------------------------- tickers
def fetch_yahoo(tickers):
    out = {}
    for t in tickers:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
               "?range=1d&interval=1d")
        try:
            meta = json.loads(get(url))["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            ts = meta.get("regularMarketTime")
            asof = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""
            if price is None:
                raise ValueError("no regularMarketPrice in response")
            out[t] = (price, asof)
            print(f"  {t:8} {price:>10.2f}  {asof}")
        except Exception as e:
            print(f"  {t:8} FAILED: {e}")
    return out


# ------------------------------------------------------------------- TIPS
FEDINVEST = "https://www.treasurydirect.gov/GA-FI/FedInvest"


def fedinvest_csv(d, tries=3):
    """FedInvest's price file for date d, as CSV text ("" if none that day).

    The site needs a session: submit the date form, then the results page's
    CSV form. Each form carries a CSRF token, so their fields are read from
    the page rather than built here.
    """
    def form_fields(page, form_id):
        m = re.search(rf'<form id="{form_id}".*?</form>', page, re.S)
        if not m:
            return None
        return dict(re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"',
                               m.group(0)))

    for attempt in range(1, tries + 1):
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def fetch(path, form=None):
            data = urllib.parse.urlencode(form).encode() if form else None
            req = urllib.request.Request(f"{FEDINVEST}/{path}", data=data,
                                         headers=UA)
            with opener.open(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")

        try:
            form = form_fields(fetch("selectSecurityPriceDate"), "fromToDate")
            if form is None:
                raise RuntimeError("FedInvest date form not found")
            form["priceDate"] = d.isoformat()
            # redirects to the results page
            csv_form = form_fields(fetch("selectSecurityPriceDate", form),
                                   "CSVFormat")
            if csv_form is None:                       # no prices that day
                return ""
            body = fetch("securityPriceDetail", csv_form)
            break
        except Exception as e:
            if attempt == tries:
                raise
            print(f"  retry {attempt}/{tries - 1} after error: {e}")
    if DEBUG:
        fn = DATA / f"debug_fedinvest_{d}.txt"
        fn.write_text(body)
        print(f"  [debug] FedInvest {d} -> {fn.name} ({len(body)} bytes)")
    return body


def fetch_fedinvest_prices(cusips, lookback=7):
    """Latest FedInvest end-of-day clean prices for the given CUSIPs.

    Tries today first, then walks back up to `lookback` days to find the
    most recent business day with data.
    """
    wanted = set(cusips)
    d = date.today()
    for _ in range(lookback):
        try:
            body = fedinvest_csv(d)
        except Exception as e:
            print(f"  FedInvest request failed for {d}: {e}")
            body = ""
        prices = {}
        for line in body.splitlines():
            parts = [p.strip().strip('"') for p in line.split(",")]
            if parts and parts[0] in wanted:
                # CUSIP, type, rate, maturity, call, buy, sell, end-of-day
                # Intraday the end-of-day column is 0.0; fall back to the
                # buy/sell midpoint, and treat all-zero as no data yet.
                try:
                    buy, sell, eod = (float(parts[-3]), float(parts[-2]),
                                      float(parts[-1]))
                except (ValueError, IndexError):
                    continue
                price = eod or (buy and sell and (buy + sell) / 2) \
                    or sell or buy
                if price:
                    prices[parts[0]] = price
        if prices:
            print(f"  FedInvest prices as of {d}: {len(prices)}/{len(wanted)} CUSIPs")
            return prices, d
        d -= timedelta(days=1)
    return {}, None


def fetch_ref_cpi_dated(cusips):
    """refCpiOnDatedDate per CUSIP from TreasuryDirect, cached in REF_CSV."""
    cache = {}
    if REF_CSV.exists():
        with open(REF_CSV) as f:
            cache = {r["cusip"]: float(r["ref_cpi_dated"])
                     for r in csv.DictReader(f)}
    missing = [c for c in cusips if c not in cache]
    for c in missing:
        url = f"https://www.treasurydirect.gov/TA_WS/securities/search?cusip={c}&format=json"
        try:
            recs = json.loads(get(url))
            vals = [float(r["refCpiOnDatedDate"]) for r in recs
                    if r.get("refCpiOnDatedDate")]
            if not vals:
                raise ValueError("no refCpiOnDatedDate in response")
            cache[c] = vals[0]
            print(f"  {c} refCPI(dated) = {vals[0]}")
        except Exception as e:
            print(f"  {c} FAILED refCPI lookup: {e}")
    with open(REF_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cusip", "ref_cpi_dated"])
        for c, v in sorted(cache.items()):
            w.writerow([c, v])
    return cache


def fetch_cpi_series():
    """CPI-U NSA (CUUR0000SA0) monthly series, BLS API v2 primary
    (keyless, reliable), FRED CSV as fallback (Akamai-guarded, flaky)."""
    try:
        y = date.today().year
        payload = json.dumps({"seriesid": ["CUUR0000SA0"],
                              "startyear": str(y - 1), "endyear": str(y)})
        # Normally answers in <1s; a stalled connection is better retried than
        # waited out, since the FRED fallback is unreliable.
        resp = json.loads(get("https://api.bls.gov/publicAPI/v2/timeseries/data/",
                              data=payload.encode(), timeout=15,
                              headers={"Content-Type": "application/json"}))
        series = {}
        for item in resp["Results"]["series"][0]["data"]:
            if not item["period"].startswith("M"):
                continue
            try:
                value = float(item["value"])
            except ValueError:      # "-" placeholder for unpublished months
                continue
            series[(int(item["year"]), int(item["period"][1:]))] = value
        if series:
            return series
        raise ValueError(f"BLS returned no data: {resp.get('message')}")
    except Exception as e:
        print(f"  BLS CPI fetch failed ({e}); trying FRED ...")
    body = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS")
    series = {}
    for row in csv.reader(body.splitlines()[1:]):
        try:
            d = datetime.strptime(row[0], "%Y-%m-%d").date()
            series[(d.year, d.month)] = float(row[1])
        except (ValueError, IndexError):
            pass
    return series


def ref_cpi(d, cpi):
    """Daily Ref CPI: interpolate CPI of month m-3 to m-2 across month m."""
    def month_add(y, m, k):
        m += k
        return (y + (m - 1) // 12, (m - 1) % 12 + 1)
    y3, m3 = month_add(d.year, d.month, -3)
    y2, m2 = month_add(d.year, d.month, -2)
    if (y3, m3) not in cpi or (y2, m2) not in cpi:
        raise ValueError(f"CPI not yet published for months needed by {d}")
    days_in_month = (date(*month_add(d.year, d.month, 1), 1) - date(d.year, d.month, 1)).days
    return cpi[(y3, m3)] + (d.day - 1) / days_in_month * (cpi[(y2, m2)] - cpi[(y3, m3)])


def next_business_day(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def main():
    global DEBUG
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true",
                    help="save raw HTTP responses to data/ for troubleshooting")
    args = ap.parse_args()
    DEBUG = args.debug

    tickers, tips = read_inputs()
    print(f"Fetching {len(tickers)} ticker quotes ...")
    quotes = fetch_yahoo(tickers)
    with open(PRICES_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "price", "asof"])
        for t, (p, asof) in quotes.items():
            w.writerow([t, p, asof])
    print(f"Wrote {PRICES_CSV} ({len(quotes)}/{len(tickers)} tickers)")

    cusips = [c for c, _ in tips]
    print(f"\nFetching TIPS prices for {len(cusips)} CUSIPs ...")
    prices, price_date = fetch_fedinvest_prices(cusips)
    ref_dated = fetch_ref_cpi_dated(cusips)
    try:
        cpi = fetch_cpi_series()
    except Exception as e:
        print(f"  CPI fetch from FRED failed ({e}) — index ratios will be "
              "blank; rerun or fill tips_prices.csv manually")
        cpi = {}
    settle = next_business_day(date.today())

    n = 0
    with open(TIPS_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cusip", "clean_price", "index_ratio", "price_date"])
        for c in cusips:
            price = prices.get(c)
            try:
                ratio = round(ref_cpi(settle, cpi) / ref_dated[c], 5) \
                    if c in ref_dated else None
            except ValueError as e:
                print(f"  {c}: {e}")
                ratio = None
            if price is None or ratio is None:
                print(f"  {c} INCOMPLETE (price={price}, ratio={ratio}) — "
                      "row written with blanks; fill manually if needed")
            w.writerow([c, price if price is not None else "",
                        ratio if ratio is not None else "", price_date or ""])
            n += price is not None and ratio is not None
    print(f"Wrote {TIPS_CSV} ({n}/{len(cusips)} complete)")

    if len(quotes) < len(tickers) or n < len(cusips):
        sys.exit(1)


if __name__ == "__main__":
    main()
