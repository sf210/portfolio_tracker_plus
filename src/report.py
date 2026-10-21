#!/usr/bin/env python3
"""Generate the portfolio allocation report.

Reads:
  src/portfolio_input.xlsx   (edited in LibreOffice Calc)
  data/prices.csv            (from fetch_prices.py)
  data/tips_prices.csv       (from fetch_prices.py)

Writes:
  output/portfolio_report.html   self-contained, no external resources

TIPS positions are valued at face * index_ratio * clean_price / 100 and
carried as asset class "TIPS", which rolls up into the U.S. Bonds category.

Usage:
  ~/finance/planning/.venv/bin/python src/report.py \
      [--prices data/prices.csv] [--tips data/tips_prices.csv] \
      [-o output/portfolio_report.html]
"""

import argparse
import csv
import html
import sys
import webbrowser
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- loading
def load_inputs(wb_path):
    wb = openpyxl.load_workbook(wb_path, data_only=True)

    def rows(sheet):
        for r in wb[sheet].iter_rows(min_row=2, values_only=True):
            if any(v not in (None, "") for v in r):
                yield r

    accounts = {r[0]: {"type": r[1], "institution": r[2], "owner": r[3],
                       "tax": r[4]} for r in rows("Accounts")}
    # column D (Broker Price) is filled by linked_accounts.py fetch
    holdings = [{"account": r[0], "ticker": r[1], "shares": r[2],
                 "broker_price": r[3] if len(r) > 3 else None}
                for r in rows("Holdings")]
    tips = [{"account": r[0], "cusip": r[1], "face": r[2], "coupon": r[3],
             "maturity": r[4], "desc": r[5],
             "cost": r[6] if len(r) > 6 else None} for r in rows("TIPS")]
    assets = defaultdict(list)   # ticker -> [(class, pct)]
    overrides = {}
    names = {}
    for r in rows("Assets"):
        ticker, name, cls, pct, override = r[:5]
        names[ticker] = name
        if override is not None:
            overrides[ticker] = float(override)
        if cls is None:     # added by fetch_composition, class not filled in yet
            continue
        assets[ticker].append((cls, pct if pct is not None else 1.0))
    targets = {r[0]: {"category": r[1], "parent": r[2],
                      "target": r[3] or 0, "threshold": r[4] or 0}
               for r in rows("Targets")}
    return accounts, holdings, tips, assets, overrides, names, targets


def load_prices(path):
    prices = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            prices[r["ticker"]] = (float(r["price"]), r.get("asof", ""))
    return prices


def load_tips_prices(path):
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            try:
                out[r["cusip"]] = (float(r["clean_price"]),
                                   float(r["index_ratio"]),
                                   r.get("price_date", ""))
            except ValueError:
                pass   # incomplete row; reported as a warning later
    return out


# ------------------------------------------------------------ computation
def compute(accounts, holdings, tips, assets, overrides, names, targets,
            prices, tips_prices):
    positions = []      # account, label, class, value  (one row per class slice)
    detail = []         # per-holding table rows
    warnings = []

    for h in holdings:
        t = h["ticker"]
        if t in overrides:
            price, asof = overrides[t], "fixed"
        elif t in prices:
            price, asof = prices[t]
        elif h.get("broker_price") is not None:
            price, asof = h["broker_price"], "broker"
        else:
            warnings.append(f"No price for {t} ({h['account']}) — holding skipped")
            continue
        value = h["shares"] * price
        classes = assets.get(t) or [("Unclassified", 1.0)]
        if t not in assets:
            w = (f"{t} has no Class on the Assets sheet" if t in names
                 else f"{t} missing from Assets sheet") + " — class Unclassified"
            if w not in warnings:
                warnings.append(w)
        for cls, pct in classes:
            positions.append((h["account"], t, cls, value * pct))
        detail.append({"account": h["account"], "label": t,
                       "name": names.get(t, ""), "shares": h["shares"],
                       "price": price, "value": value,
                       "cls": " / ".join(c for c, _ in classes)})

    tips_detail = []
    for b in tips:
        info = tips_prices.get(b["cusip"])
        if not info:
            warnings.append(f"No TIPS price/ratio for {b['cusip']} — skipped")
            continue
        price, ratio, pdate = info
        value = b["face"] * ratio * price / 100
        positions.append((b["account"], b["cusip"], "TIPS", value))
        mat = b["maturity"]
        mat = mat.date() if isinstance(mat, datetime) else mat
        tips_detail.append({**b, "maturity": mat, "price": price,
                            "ratio": ratio, "value": value, "pdate": pdate,
                            "adj": b["face"] * ratio})

    total = sum(v for *_, v in positions)
    by_class = defaultdict(float)
    by_account = defaultdict(float)
    for acct, _, cls, v in positions:
        by_class[cls] += v
        by_account[acct] += v
    by_tax = defaultdict(float)
    for acct, v in by_account.items():
        tax = accounts.get(acct, {}).get("tax") or "Unknown"
        if acct not in accounts:
            warnings.append(f"Account '{acct}' not in Accounts sheet")
        by_tax[tax] += v
    by_category = defaultdict(float)
    by_parent = defaultdict(float)
    for cls, v in by_class.items():
        tgt = targets.get(cls, {})
        by_category[tgt.get("category", cls)] += v
        by_parent[tgt.get("parent", "Other")] += v

    alloc = []
    for cls in list(targets) + [c for c in by_class if c not in targets]:
        actual = by_class.get(cls, 0) / total if total else 0
        tgt = targets.get(cls, {"category": cls, "parent": "Other",
                                "target": 0, "threshold": 0})
        diff = actual - tgt["target"]
        flag = tgt["threshold"] > 0 and abs(diff) > tgt["threshold"]
        alloc.append({"cls": cls, "value": by_class.get(cls, 0),
                      "actual": actual, "diff": diff, "flag": flag, **tgt})

    return {"positions": positions, "detail": detail, "tips": tips_detail,
            "cashflows": tips_cashflows(tips_detail),
            "total": total, "alloc": alloc, "by_account": dict(by_account),
            "by_tax": dict(by_tax), "by_category": dict(by_category),
            "by_parent": dict(by_parent), "warnings": warnings}


def tips_cashflows(tips_detail):
    """Projected cash flows per year in today's dollars: semiannual coupons
    on the inflation-adjusted principal (at the current index ratio) plus
    principal repayment at maturity. year -> {"coupons": x, "principal": y}.
    """
    flows = defaultdict(lambda: {"coupons": 0.0, "principal": 0.0})
    today = date.today()
    for t in tips_detail:
        mat = t["maturity"]
        m2, dd = mat.month, mat.day
        m1 = m2 + 6 if m2 <= 6 else m2 - 6
        payment = t["adj"] * t["coupon"] / 200   # coupon is in percent
        for y in range(today.year, mat.year + 1):
            for m in (m1, m2):
                pd = date(y, m, dd)
                if today < pd <= mat:
                    flows[y]["coupons"] += payment
        flows[mat.year]["principal"] += t["adj"]
    return dict(flows)


# ---------------------------------------------------------------- helpers
def usd(v, cents=False):
    return f"${v:,.2f}" if cents else f"${v:,.0f}"


def pct(v, dp=1):
    return f"{v * 100:.{dp}f}%"


def esc(s):
    return html.escape(str(s))


def bar_path(x0, y, w, h, r=4):
    """Horizontal bar: square at baseline (x0), rounded at the data end."""
    if w <= r:
        return f"M{x0},{y} h{max(w, 0.5)} v{h} h{-max(w, 0.5)} Z"
    x1 = x0 + w
    return (f"M{x0},{y} H{x1 - r} Q{x1},{y} {x1},{y + r} V{y + h - r} "
            f"Q{x1},{y + h} {x1 - r},{y + h} H{x0} Z")


def bar_path_left(x1, y, w, h, r=4):
    """Horizontal bar growing leftward from baseline x1; rounded left end."""
    if w <= r:
        return f"M{x1},{y} h{-max(w, 0.5)} v{h} h{max(w, 0.5)} Z"
    x0 = x1 - w
    return (f"M{x1},{y} H{x0 + r} Q{x0},{y} {x0},{y + r} V{y + h - r} "
            f"Q{x0},{y + h} {x0 + r},{y + h} H{x1} Z")


GUTTER = 150
BAR_H, GAP = 22, 8


def hbar_svg(rows, fmt=lambda v: usd(v), width=660):
    """Single-hue horizontal bar chart. rows = [(label, value, tooltip)]."""
    if not rows:
        return ""
    vmax = max(v for _, v, _ in rows) or 1
    plot_w = width - GUTTER - 90
    height = len(rows) * (BAR_H + GAP) + 10
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'style="width:100%;max-width:{width}px;height:auto">']
    for i, (label, v, tip) in enumerate(rows):
        y = 5 + i * (BAR_H + GAP)
        w = v / vmax * plot_w
        parts.append(
            f'<text x="{GUTTER - 8}" y="{y + BAR_H - 6}" text-anchor="end" '
            f'class="lbl">{esc(label)}</text>'
            f'<path d="{bar_path(GUTTER, y, w, BAR_H)}" fill="var(--series-1)" '
            f'data-tip="{esc(tip)}"/>'
            f'<text x="{GUTTER + w + 6}" y="{y + BAR_H - 6}" class="val">'
            f'{esc(fmt(v))}</text>')
    parts.append(f'<line x1="{GUTTER}" y1="0" x2="{GUTTER}" y2="{height}" '
                 'class="axis"/></svg>')
    return "".join(parts)


def diverging_svg(rows, width=660):
    """Diverging bars around zero. rows = [(label, diff, tooltip, flagged)]."""
    if not rows:
        return ""
    vmax = max(abs(d) for _, d, _, _ in rows) or 0.01
    plot_w = (width - GUTTER - 100) / 2
    xc = GUTTER + plot_w
    height = len(rows) * (BAR_H + GAP) + 10
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'style="width:100%;max-width:{width}px;height:auto">']
    for i, (label, d, tip, flagged) in enumerate(rows):
        y = 5 + i * (BAR_H + GAP)
        w = abs(d) / vmax * plot_w
        color = "var(--div-pos)" if d >= 0 else "var(--div-neg)"
        path = (bar_path(xc, y, w, BAR_H) if d >= 0
                else bar_path_left(xc, y, w, BAR_H))
        tx = xc + w + 6 if d >= 0 else xc - w - 6
        anchor = "start" if d >= 0 else "end"
        mark = " ⚠" if flagged else ""
        parts.append(
            f'<text x="{GUTTER - 8}" y="{y + BAR_H - 6}" text-anchor="end" '
            f'class="lbl">{esc(label)}</text>'
            f'<path d="{path}" fill="{color}" data-tip="{esc(tip)}"/>'
            f'<text x="{tx}" y="{y + BAR_H - 6}" text-anchor="{anchor}" '
            f'class="val">{d * 100:+.1f}pp{mark}</text>')
    parts.append(f'<line x1="{xc}" y1="0" x2="{xc}" y2="{height}" class="axis"/>'
                 '</svg>')
    return "".join(parts)


def column_svg(rows, width=660, height=200):
    """Column chart. rows = [(label, value, tooltip)]."""
    if not rows:
        return ""
    vmax = max(v for _, v, _ in rows) or 1
    n = len(rows)
    pad_l, pad_b, pad_t = 10, 22, 14
    plot_h = height - pad_b - pad_t
    slot = (width - pad_l * 2) / n
    bw = min(slot - 2, 46)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'style="width:100%;max-width:{width}px;height:auto">']
    for i, (label, v, tip) in enumerate(rows):
        h = v / vmax * plot_h
        x = pad_l + i * slot + (slot - bw) / 2
        y = pad_t + plot_h - h
        r = 4 if h > 4 else 0
        parts.append(
            f'<path d="M{x},{y + h} V{y + r} Q{x},{y} {x + r},{y} H{x + bw - r} '
            f'Q{x + bw},{y} {x + bw},{y + r} V{y + h} Z" fill="var(--series-1)" '
            f'data-tip="{esc(tip)}"/>'
            f'<text x="{x + bw / 2}" y="{height - 6}" text-anchor="middle" '
            f'class="lbl">{esc(label)}</text>'
            f'<text x="{x + bw / 2}" y="{y - 4}" text-anchor="middle" '
            f'class="val">{usd(v / 1000)}k</text>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - pad_l}" '
                 f'y2="{pad_t + plot_h}" class="axis"/></svg>')
    return "".join(parts)


def stacked_column_svg(rows, width=660, height=230, line=None):
    """Stacked columns. rows = [(label, [(value, color_var, tooltip), ...])].
    Bottom segment sits on the baseline; 2px surface gaps between segments;
    the topmost segment gets the rounded data-end. Labels every 5th column.
    line = [(value, tooltip), ...] (same length as rows) overlays a polyline.
    """
    if not rows:
        return ""
    vmax = max(sum(v for v, _, _ in segs) for _, segs in rows) or 1
    if line:
        vmax = max(vmax, max(v for v, _ in line))
    pad_l, pad_r, pad_b, pad_t = 54, 10, 22, 8
    plot_h = height - pad_b - pad_t
    slot = (width - pad_l - pad_r) / len(rows)
    bw = min(slot - 2, 34)
    # y gridlines on a nice step, about three lines
    step = 10 ** len(str(int(vmax / 3))) // 2 or 1
    step = max(step, int(vmax / 6))
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'style="width:100%;max-width:{width}px;height:auto">']
    g = step
    while g < vmax * 1.02:
        gy = pad_t + plot_h - g / vmax * plot_h
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" '
                     f'y2="{gy:.1f}" class="grid"/>'
                     f'<text x="{pad_l - 6}" y="{gy + 4:.1f}" text-anchor="end" '
                     f'class="lbl">${g / 1000:,.0f}k</text>')
        g += step
    for i, (label, segs) in enumerate(rows):
        x = pad_l + i * slot + (slot - bw) / 2
        y = pad_t + plot_h
        segs = [(v, c, tip) for v, c, tip in segs if v > 0]
        for j, (v, color, tip) in enumerate(segs):
            h = v / vmax * plot_h
            y -= h
            top = j == len(segs) - 1
            r = 3 if top and h > 3 else 0
            parts.append(
                f'<path d="M{x},{y + h:.1f} V{y + r:.1f} Q{x},{y:.1f} '
                f'{x + r},{y:.1f} H{x + bw - r} Q{x + bw},{y:.1f} '
                f'{x + bw},{y + r:.1f} V{y + h:.1f} Z" fill="{color}" '
                f'stroke="var(--surface)" stroke-width="1" '
                f'data-tip="{esc(tip)}"/>')
            y -= 1   # 2px-ish surface gap before the next segment
        if i % 5 == 0 or i == len(rows) - 1:
            parts.append(f'<text x="{x + bw / 2}" y="{height - 6}" '
                         f'text-anchor="middle" class="lbl">{esc(label)}</text>')
    if line:
        pts, dots = [], []
        for i, (v, tip) in enumerate(line):
            lx = pad_l + i * slot + slot / 2
            ly = pad_t + plot_h - v / vmax * plot_h
            pts.append(f"{lx:.1f},{ly:.1f}")
            dots.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" '
                        f'fill="var(--series-3)"/>'
                        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="9" '
                        f'fill="transparent" data-tip="{esc(tip)}"/>')
        parts.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                     f'stroke="var(--series-3)" stroke-width="2" '
                     f'stroke-linejoin="round"/>' + "".join(dots))
    parts.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" '
                 f'x2="{width - pad_r}" y2="{pad_t + plot_h}" class="axis"/>'
                 '</svg>')
    return "".join(parts)


def table(headers, rows, aligns=None, totals=None):
    aligns = aligns or ["left"] * len(headers)
    th = "".join(f'<th style="text-align:{a}">{esc(h)}</th>'
                 for h, a in zip(headers, aligns))
    body = ""
    for r in rows:
        tds = "".join(f'<td style="text-align:{a}">{c}</td>'
                      for c, a in zip(r, aligns))
        body += f"<tr>{tds}</tr>"
    if totals:
        tds = "".join(f'<td style="text-align:{a}">{c}</td>'
                      for c, a in zip(totals, aligns))
        body += f'<tr class="totals">{tds}</tr>'
    return (f'<div class="tblwrap"><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


# ------------------------------------------------------------------ html
CSS = """
:root { color-scheme: light dark; }
body {
  margin: 0; padding: 24px; background: var(--page);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  color: var(--ink); max-width: 1100px; margin-inline: auto;
}
body {
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --axis-c:#c3c2b7;
  --series-1:#2a78d6; --series-2:#008300; --series-3:#e87ba4;
  --div-pos:#2a78d6; --div-neg:#e34948;
  --good:#0ca30c; --serious:#ec835a; --critical:#d03b3b;
  --border:rgba(11,11,11,0.10);
}
@media (prefers-color-scheme: dark) {
  body {
    --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7;
    --muted:#898781; --grid:#2c2c2a; --axis-c:#383835;
    --series-1:#3987e5; --series-2:#008300; --series-3:#d55181;
    --div-pos:#3987e5; --div-neg:#e66767;
    --border:rgba(255,255,255,0.10);
  }
}
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 0 0 12px; }
.sub { color: var(--ink2); font-size: 13px; margin-bottom: 20px; }
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 18px 20px; margin-bottom: 18px;
}
.kpis { display: flex; flex-wrap: wrap; gap: 18px; }
.kpis .card { flex: 1 1 150px; margin-bottom: 0; }
.kpi-label { font-size: 12px; color: var(--ink2); margin-bottom: 6px; }
.kpi-value { font-size: 34px; font-weight: 650; }
.kpi-note { font-size: 12px; color: var(--muted); margin-top: 4px; }
.hero { font-size: 48px; font-weight: 700; }
svg .lbl { font: 12px system-ui, sans-serif; fill: var(--muted); }
svg .val { font: 12px system-ui, sans-serif; fill: var(--ink2);
           font-variant-numeric: tabular-nums; }
svg .axis { stroke: var(--axis-c); stroke-width: 1; }
svg .grid { stroke: var(--grid); stroke-width: 1; }
tr.totals td { font-weight: 650; border-top: 2px solid var(--axis-c); }
svg path[data-tip]:hover { opacity: 0.85; }
.legend { display: flex; gap: 16px; font-size: 12px; color: var(--ink2);
          margin: 6px 0 10px; }
.chip { display: inline-block; width: 10px; height: 10px; border-radius: 3px;
        margin-right: 5px; vertical-align: baseline; }
.chip.line { height: 3px; border-radius: 2px; vertical-align: middle; }
.tblwrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--grid);
     padding: 6px 10px; }
td { padding: 6px 10px; border-bottom: 1px solid var(--grid);
     font-variant-numeric: tabular-nums; }
.status { font-weight: 600; }
.status.ok { color: var(--good); }
.status.bad { color: var(--critical); }
.warn-list { color: var(--critical); font-size: 13px; }
#tip { position: fixed; pointer-events: none; background: var(--ink);
       color: var(--page); padding: 6px 10px; border-radius: 6px;
       font-size: 12px; display: none; z-index: 10; max-width: 320px; }
"""

JS = """
const tip = document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el => {
  el.addEventListener('mousemove', e => {
    tip.textContent = el.dataset.tip;
    tip.style.display = 'block';
    tip.style.left = Math.min(e.clientX + 14, innerWidth - 340) + 'px';
    tip.style.top = (e.clientY + 14) + 'px';
  });
  el.addEventListener('mouseleave', () => tip.style.display = 'none');
});
"""


def build_html(res, accounts, asof_note):
    total = res["total"]
    stocks = res["by_parent"].get("Stocks", 0)
    bonds = res["by_parent"].get("Bonds", 0)
    short = res["by_parent"].get("Short term", 0)
    tips_total = sum(t["value"] for t in res["tips"])

    kpis = f"""
    <div class="kpis">
      <div class="card"><div class="kpi-label">Total portfolio</div>
        <div class="kpi-value hero">{usd(total)}</div>
        <div class="kpi-note">{asof_note}</div></div>
      <div class="card"><div class="kpi-label">Stocks</div>
        <div class="kpi-value">{pct(stocks / total)}</div>
        <div class="kpi-note">{usd(stocks)}</div></div>
      <div class="card"><div class="kpi-label">Bonds</div>
        <div class="kpi-value">{pct(bonds / total)}</div>
        <div class="kpi-note">{usd(bonds)}</div></div>
      <div class="card"><div class="kpi-label">Short term</div>
        <div class="kpi-value">{pct(short / total)}</div>
        <div class="kpi-note">{usd(short)}</div></div>
      <div class="card"><div class="kpi-label">TIPS ladder</div>
        <div class="kpi-value">{usd(tips_total)}</div>
        <div class="kpi-note">{len(res["tips"])} bonds, in U.S. Bonds</div></div>
    </div>"""

    # --- allocation vs target ------------------------------------------
    alloc = [a for a in res["alloc"] if a["value"] > 0 or a["target"] > 0]
    div_rows = [(a["cls"], a["diff"],
                 f'{a["cls"]}: actual {pct(a["actual"])} vs target '
                 f'{pct(a["target"])} ({a["diff"] * 100:+.1f}pp, threshold '
                 f'±{a["threshold"] * 100:.1f}pp)', a["flag"])
                for a in alloc]
    alloc_tbl = table(
        ["Class", "Category", "Value", "Actual", "Target", "Diff", "Status"],
        [[esc(a["cls"]), esc(a["category"]), usd(a["value"]),
          pct(a["actual"]), pct(a["target"]), f'{a["diff"] * 100:+.1f}pp',
          ('<span class="status bad">⚠ rebalance</span>' if a["flag"]
           else '<span class="status ok">✓ in band</span>')]
         for a in alloc],
        ["left", "left", "right", "right", "right", "right", "left"])

    # --- by class / account / tax --------------------------------------
    class_rows = sorted(((a["cls"], a["value"],
                          f'{a["cls"]}: {usd(a["value"])} ({pct(a["actual"])})')
                         for a in alloc if a["value"] > 0),
                        key=lambda r: -r[1])
    acct_rows = sorted(((k, v, f'{k} ({accounts.get(k, {}).get("tax", "?")}, '
                         f'{accounts.get(k, {}).get("institution", "?")}): '
                         f'{usd(v)} ({pct(v / total)})')
                        for k, v in res["by_account"].items() if v > 0),
                       key=lambda r: -r[1])
    tax_tbl = table(["Tax type", "Value", "Share"],
                    [[esc(k), usd(v), pct(v / total)]
                     for k, v in sorted(res["by_tax"].items(),
                                        key=lambda kv: -kv[1])],
                    ["left", "right", "right"])

    # --- TIPS ------------------------------------------------------------
    tips_cols = [(str(t["maturity"].year), t["value"],
                  f'{t["desc"]} ({t["cusip"]}): {usd(t["value"])} — '
                  f'{t["coupon"]}% coupon, ratio {t["ratio"]:.5f}, '
                  f'price {t["price"]:.4f}')
                 for t in sorted(res["tips"], key=lambda t: t["maturity"])]
    tips_tbl = table(
        ["CUSIP", "Description", "Maturity", "Coupon", "Face", "Index ratio",
         "Price", "Market value"],
        [[esc(t["cusip"]), esc(t["desc"]), str(t["maturity"]),
          f'{t["coupon"]}%', usd(t["face"]), f'{t["ratio"]:.5f}',
          f'{t["price"]:.4f}', usd(t["value"])]
         for t in sorted(res["tips"], key=lambda t: t["maturity"])],
        ["left", "left", "left", "right", "right", "right", "right", "right"])

    # --- TIPS hold-to-maturity -----------------------------------------
    tips_sorted = sorted(res["tips"], key=lambda t: t["maturity"])
    have_cost = [t for t in tips_sorted if t["cost"]]
    tot_adj = sum(t["adj"] for t in tips_sorted)
    tot_mkt = sum(t["value"] for t in tips_sorted)
    tot_cost = sum(t["cost"] for t in have_cost)

    def gain_cell(g):
        cls = "ok" if g >= 0 else "bad"
        return f'<span class="status {cls}">{"+" if g >= 0 else "−"}{usd(abs(g))}</span>'

    htm_rows = []
    for t in tips_sorted:
        cost = t["cost"]
        htm_rows.append(
            [esc(t["cusip"]), esc(t["desc"]), str(t["maturity"]),
             usd(t["face"]), f'{t["ratio"]:.5f}', usd(t["adj"]),
             usd(cost) if cost else "—", usd(t["value"]),
             gain_cell(t["value"] - cost) if cost else "—"])
    htm_tbl = table(
        ["CUSIP", "Description", "Maturity", "Face", "Index ratio",
         "Adj. principal", "Cost basis", "Market value", "Unrealized"],
        htm_rows,
        ["left", "left", "left", "right", "right", "right", "right",
         "right", "right"],
        totals=["Total", "", "", usd(sum(t["face"] for t in tips_sorted)), "",
                usd(tot_adj), usd(tot_cost) if have_cost else "—",
                usd(tot_mkt),
                gain_cell(sum(t["value"] - t["cost"] for t in have_cost))
                if have_cost else "—"])
    htm_note = (f"Adjusted principal = face × index ratio: what the ladder "
                f"repays at maturity in today's dollars ({usd(tot_adj)}), vs "
                f"{usd(tot_mkt)} at market. Actual repayments will also carry "
                f"future inflation adjustment.")

    # --- TIPS cash flows -------------------------------------------------
    cf = res["cashflows"]
    cf_rows, cf_line = [], []
    if cf:
        years = list(range(min(cf), max(cf) + 1))
        totals = []
        for y in years:
            f = cf.get(y, {"coupons": 0, "principal": 0})
            segs = [(f["principal"], "var(--series-1)",
                     f'{y} principal: {usd(f["principal"])}'),
                    (f["coupons"], "var(--series-2)",
                     f'{y} coupons: {usd(f["coupons"])}')]
            cf_rows.append((str(y), segs))
            totals.append(f["principal"] + f["coupons"])
        # trailing 5-yr moving average of total cash flow; the first five
        # years use the cumulative (expanding) average
        for i, y in enumerate(years):
            window = totals[max(0, i - 4):i + 1]
            ma = sum(window) / len(window)
            cf_line.append((ma, f'{y} 5-yr avg cash flow: {usd(ma)}'))
    tot_coupons = sum(f["coupons"] for f in cf.values())
    cf_note = (f"Real (today's-dollar) cash flows at the current index "
               f"ratio: {usd(tot_coupons)} total coupons + {usd(tot_adj)} "
               f"principal through {max(cf) if cf else '—'}. The 5-year "
               f"moving average is trailing (cumulative average for the "
               f"first five years).")
    cf_mean_html = ""
    mat_years = [y for y, f in cf.items() if f["principal"] > 0]
    if mat_years:
        first_mat = min(mat_years)
        span = [y for y in cf if y >= first_mat]
        mean = sum(cf[y]["coupons"] + cf[y]["principal"]
                   for y in span) / (max(span) - first_mat + 1)
        cf_mean_html = (
            f'<div style="margin-top:12px"><span class="kpi-label">'
            f'Mean annual distribution, {first_mat}–{max(span)} '
            f'(first maturity onward)</span><br>'
            f'<span class="kpi-value">{usd(mean)}</span></div>')

    holdings_tbl = table(
        ["Account", "Ticker", "Name", "Class", "Shares", "Price", "Value"],
        [[esc(d["account"]), esc(d["label"]), esc(d["name"]), esc(d["cls"]),
          f'{d["shares"]:,.0f}', f'{d["price"]:,.2f}', usd(d["value"])]
         for d in sorted(res["detail"], key=lambda d: -d["value"])],
        ["left", "left", "left", "left", "right", "right", "right"])

    warn_html = ""
    if res["warnings"]:
        items = "".join(f"<li>{esc(w)}</li>" for w in res["warnings"])
        warn_html = (f'<div class="card"><h2>⚠ Warnings</h2>'
                     f'<ul class="warn-list">{items}</ul></div>')

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Portfolio Report {date.today()}</title>
<style>{CSS}</style></head><body>
<h1>Portfolio Report</h1>
<div class="sub">Generated {datetime.now():%Y-%m-%d %H:%M} · {asof_note}</div>
{warn_html}
{kpis}
<div class="card" style="margin-top:18px"><h2>Allocation vs target</h2>
  <div class="legend">
    <span><span class="chip" style="background:var(--div-pos)"></span>Over target</span>
    <span><span class="chip" style="background:var(--div-neg)"></span>Under target</span>
    <span>⚠ = outside rebalance threshold</span>
  </div>
  {diverging_svg(div_rows)}
  {alloc_tbl}
</div>
<div class="card"><h2>Value by asset class</h2>{hbar_svg(class_rows)}</div>
<div class="card"><h2>Value by account</h2>{hbar_svg(acct_rows)}</div>
<div class="card"><h2>By tax treatment</h2>{tax_tbl}</div>
<div class="card"><h2>TIPS ladder by maturity</h2>
  {column_svg(tips_cols)}
  {tips_tbl}
</div>
<div class="card"><h2>TIPS hold-to-maturity view</h2>
  <div class="sub" style="margin-bottom:10px">{esc(htm_note)}</div>
  {htm_tbl}
</div>
<div class="card"><h2>TIPS projected cash flows</h2>
  <div class="legend">
    <span><span class="chip" style="background:var(--series-1)"></span>Principal at maturity</span>
    <span><span class="chip" style="background:var(--series-2)"></span>Coupons</span>
    <span><span class="chip line" style="background:var(--series-3)"></span>5-yr avg total cash flow</span>
  </div>
  {stacked_column_svg(cf_rows, line=cf_line)}
  {cf_mean_html}
  <div class="sub" style="margin-top:10px">{esc(cf_note)}</div>
</div>
<div class="card"><h2>Holdings detail</h2>{holdings_tbl}</div>
<div id="tip"></div>
<script>{JS}</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workbook", default=ROOT / "src" / "portfolio_input.xlsx")
    ap.add_argument("--prices", default=ROOT / "data" / "prices.csv")
    ap.add_argument("--tips", default=ROOT / "data" / "tips_prices.csv")
    ap.add_argument("-o", "--output",
                    default=ROOT / "output" / "portfolio_report.html")
    ap.add_argument("--no-open", action="store_true",
                    help="don't open the report in the default browser")
    args = ap.parse_args()

    for p in (args.workbook, args.prices, args.tips):
        if not Path(p).exists():
            sys.exit(f"Missing {p}"
                     + ("" if str(p).endswith(".xlsx")
                        else " — run src/fetch_prices.py first"))

    accounts, holdings, tips, assets, overrides, names, targets = \
        load_inputs(args.workbook)
    prices = load_prices(args.prices)
    tips_prices = load_tips_prices(args.tips)
    res = compute(accounts, holdings, tips, assets, overrides, names, targets,
                  prices, tips_prices)

    asofs = sorted({a for _, a in prices.values() if a and a != "fixed"})
    pdates = sorted({t["pdate"] for t in res["tips"] if t["pdate"]})
    asof_note = (f"quotes as of {asofs[-1]}" if asofs else "quote dates unknown")
    if pdates:
        asof_note += f" · TIPS prices as of {pdates[-1]}"

    out = Path(args.output)
    out.parent.mkdir(exist_ok=True)
    out.write_text(build_html(res, accounts, asof_note))

    print(f"Wrote {out}")
    print(f"  Total portfolio: {usd(res['total'])}")
    for parent in ("Stocks", "Bonds", "Short term"):
        v = res["by_parent"].get(parent, 0)
        print(f"  {parent:11}: {usd(v):>14}  {pct(v / res['total'])}")
    print(f"  TIPS ladder: {usd(sum(t['value'] for t in res['tips']))} "
          f"({len(res['tips'])} bonds)")
    for w in res["warnings"]:
        print(f"  WARNING: {w}")
    flagged = [a["cls"] for a in res["alloc"] if a["flag"]]
    if flagged:
        print(f"  Rebalance flags: {', '.join(flagged)}")

    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
