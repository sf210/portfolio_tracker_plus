#!/usr/bin/env python3
"""Link brokerage logins through Plaid and pull their holdings.

Plaid holds the read-only connection: you log in to Fidelity / Vanguard /
Empower inside Plaid Link (a browser page served on localhost), and Plaid
returns an access_token that can only read account, balance and holdings
data. The token is stored locally; your institution password never touches
this program.

Files (all under config/, created mode 600, git-ignored):
  plaid_credentials.json  {"client_id": "...", "secret": "...",
                           "env": "production" | "sandbox"}
                          written by `setup`
                          (or set PLAID_CLIENT_ID / PLAID_SECRET / PLAID_ENV)
  plaid_items.json        linked logins: access tokens + account mapping

Writes:
  data/portfolio_input.xlsx  `fetch` replaces the Holdings-sheet rows of each
                            account Plaid refreshed; rows for other accounts
                            are left alone. A copy of the previous workbook
                            is saved to data/backups/ first.

Usage (`uv run linked-accounts` is the same as `uv run src/linked_accounts.py`):
  uv run linked-accounts setup          # store your Plaid keys
  uv run linked-accounts link           # opens browser, log in, map accounts
  uv run linked-accounts list           # show linked logins/accounts
  uv run linked-accounts map            # re-map Plaid accounts to workbook names
  uv run linked-accounts relink NAME    # repair a login (password/MFA changed)
  uv run linked-accounts unlink NAME    # revoke the token at Plaid and forget it
  uv run linked-accounts fetch [--dry-run]   # update the Holdings sheet

NAME is the institution name as shown by `list` (case-insensitive prefix).
"""

import argparse
import getpass
import json
import os
import secrets
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from workbook_io import WORKBOOK, backup, ensure_closed, require_workbook

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
CREDS = CONFIG / "plaid_credentials.json"
ITEMS = CONFIG / "plaid_items.json"

HOSTS = {"production": "https://production.plaid.com",
         "sandbox": "https://sandbox.plaid.com"}
LINK_JS = "https://cdn.plaid.com/link/v2/stable/link-initialize.js"
CASH_TICKER = "CASH"     # Plaid reports uninvested cash as ticker CUR:USD
BROKER = "broker"        # Holdings Price Source of an unlisted fund


# ---------------------------------------------------------------- storage
def write_private(path, obj):
    path.parent.mkdir(exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2)
    os.chmod(path, 0o600)


def load_items():
    return json.loads(ITEMS.read_text()) if ITEMS.exists() else []


def load_creds():
    c = json.loads(CREDS.read_text()) if CREDS.exists() else {}
    c = {"client_id": os.environ.get("PLAID_CLIENT_ID", c.get("client_id")),
         "secret": os.environ.get("PLAID_SECRET", c.get("secret")),
         "env": os.environ.get("PLAID_ENV", c.get("env", "production"))}
    if not (c["client_id"] and c["secret"]):
        sys.exit("No Plaid credentials yet. Run `uv run linked-accounts setup`.")
    if c["env"] not in HOSTS:
        sys.exit(f"env must be one of {', '.join(HOSTS)}, not {c['env']!r}")
    return c


def is_unlisted(security):
    """True for a security with no market quote (a plan fund or trust).

    Plaid gives such securities no close_price and attaches a proxy
    security. The proxy is a poor name match, so it is never used for
    anything else.
    """
    return (security.get("close_price") is None
            or bool(security.get("proxy_security_id")))


# ---------------------------------------------------------------- Plaid API
class PlaidError(Exception):
    def __init__(self, body):
        self.code = body.get("error_code", "")
        super().__init__(f"{self.code}: {body.get('error_message', body)}")


def plaid(creds, endpoint, **payload):
    body = json.dumps({"client_id": creds["client_id"],
                       "secret": creds["secret"], **payload}).encode()
    req = urllib.request.Request(HOSTS[creds["env"]] + endpoint, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise PlaidError(json.loads(e.read() or b"{}")) from None


def link_token(creds, access_token=None):
    args = {"client_name": "Portfolio Tracker Plus", "language": "en",
            "country_codes": ["US"],
            "user": {"client_user_id": "portfolio-tracker-plus"}}
    if access_token:                       # update mode: repair an existing item
        args["access_token"] = access_token
    else:
        args["products"] = ["investments"]
    return plaid(creds, "/link/token/create", **args)["link_token"]


# ---------------------------------------------------------- browser handoff
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Link account</title><script src="{js}"></script>
<style>body{{font:16px system-ui;margin:3em auto;max-width:36em;padding:0 1em}}</style>
</head><body><h1>Portfolio Tracker Plus</h1><p id="msg">Opening Plaid Link&hellip;</p>
<script>
const msg = t => document.getElementById("msg").textContent = t;
const send = data => fetch("/{nonce}", {{method: "POST", body: JSON.stringify(data)}})
  .then(r => r.text()).then(msg);
Plaid.create({{
  token: {token},
  onSuccess: (public_token, metadata) => {{ msg("Saving…");
    send({{public_token, metadata}}); }},
  onExit: (err) => send({{exit: true, error: err}}),
}}).open();
</script></body></html>"""


def run_link(token):
    """Serve Plaid Link on localhost; return the onSuccess payload or None."""
    nonce = secrets.token_urlsafe(16)    # only our page knows where to POST
    result = {}
    page = PAGE.format(js=LINK_JS, nonce=nonce,
                       token=json.dumps(token)).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, body, ctype="text/plain"):
            self.send_response(code)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self.reply(200, page, "text/html")
            else:
                self.reply(404, b"")

        def do_POST(self):
            if self.path != f"/{nonce}":
                return self.reply(403, b"")
            n = int(self.headers.get("Content-Length", 0))
            result.update(json.loads(self.rfile.read(n)))
            done = "cancelled" if result.get("exit") else "linked"
            self.reply(200, f"Account {done}. You can close this tab and "
                            "return to the terminal.".encode())
            threading.Thread(target=server.shutdown).start()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Opening {url} — complete the login in your browser "
          "(Ctrl-C to abort).")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return None
    finally:
        server.server_close()
    if result.get("exit"):
        err = result.get("error") or {}
        if err:
            print(f"Link exited: {err.get('error_code')}: "
                  f"{err.get('display_message') or err.get('error_message')}")
        return None
    return result


# ---------------------------------------------------------- account mapping
def workbook_accounts():
    try:
        import openpyxl
    except ImportError:
        return []
    if not WORKBOOK.exists():
        return []
    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
    return [r[0] for r in wb["Accounts"].iter_rows(min_row=2, values_only=True)
            if r and r[0]]


def map_accounts(item, names):
    """Ask which workbook Accounts row each Plaid account feeds."""
    print(f"\n{item['institution']}: map each account to a workbook account "
          f"name{' (' + ', '.join(names) + ')' if names else ''}.")
    print("Press Enter to keep the current value, '-' to ignore the account.")
    for a in item["accounts"]:
        cur = a.get("workbook_account") or ""
        label = f"  {a['name']} ({a['subtype']}, …{a['mask']})"
        ans = input(f"{label} [{cur or 'ignored'}]: ").strip()
        if ans == "-":
            a["workbook_account"] = None
        elif ans:
            # store the Accounts sheet's spelling; fetch matches on it
            ans = {n.lower(): n for n in names}.get(ans.lower(), ans)
            if names and ans not in names:
                print(f"    note: '{ans}' is not in the Accounts sheet yet")
            a["workbook_account"] = ans


def find_item(items, name):
    hits = [i for i in items
            if i["institution"].lower().startswith(name.lower())]
    if len(hits) != 1:
        sys.exit(f"'{name}' matches {len(hits)} linked logins; "
                 "see `list` for names")
    return hits[0]


# ---------------------------------------------------------------- commands
def cmd_link(creds, args):
    payload = run_link(link_token(creds))
    if not payload:
        sys.exit("Nothing linked.")
    ex = plaid(creds, "/item/public_token/exchange",
               public_token=payload["public_token"])
    inst = (payload["metadata"].get("institution") or {}).get("name", "Unknown")
    accts = plaid(creds, "/accounts/get",
                  access_token=ex["access_token"])["accounts"]
    item = {"item_id": ex["item_id"], "access_token": ex["access_token"],
            "institution": inst, "linked": date.today().isoformat(),
            "accounts": [{"account_id": a["account_id"], "name": a["name"],
                          "mask": a.get("mask") or "", "subtype": a.get("subtype")
                          or a.get("type"), "workbook_account": None}
                         for a in accts]}
    items = load_items()
    items.append(item)
    write_private(ITEMS, items)          # save the token before prompting
    print(f"Linked {inst} ({len(accts)} accounts).")
    map_accounts(item, workbook_accounts())
    write_private(ITEMS, items)
    print(f"Saved to {ITEMS}")


def cmd_list(creds, args):
    items = load_items()
    if not items:
        print("No linked logins. Run `link`.")
    for i in items:
        print(f"{i['institution']}  (linked {i['linked']}, item {i['item_id'][:8]}…)")
        for a in i["accounts"]:
            print(f"    {a['name']:40} …{a['mask']:4}  -> "
                  f"{a.get('workbook_account') or '(ignored)'}")


def cmd_map(creds, args):
    items = load_items()
    names = workbook_accounts()
    for i in items:
        map_accounts(i, names)
    write_private(ITEMS, items)


def cmd_relink(creds, args):
    items = load_items()
    item = find_item(items, args.name)
    if not run_link(link_token(creds, item["access_token"])):
        sys.exit("Relink not completed.")
    print(f"{item['institution']} repaired; the existing token works again.")


def cmd_unlink(creds, args):
    items = load_items()
    item = find_item(items, args.name)
    try:
        plaid(creds, "/item/remove", access_token=item["access_token"])
    except PlaidError as e:
        print(f"Plaid /item/remove failed ({e}); forgetting it locally anyway.")
    items.remove(item)
    write_private(ITEMS, items)
    print(f"Unlinked {item['institution']}.")


def cmd_setup(creds, args):
    print("Paste the keys from dashboard.plaid.com > Developers > Keys.")
    client_id = input("client_id: ").strip()
    env = input("Environment, production or sandbox [production]: ").strip()
    env = env or "production"
    if env not in HOSTS:
        sys.exit(f"env must be one of {', '.join(HOSTS)}")
    secret = getpass.getpass(f"{env} secret (not echoed): ").strip()
    if not (client_id and secret):
        sys.exit("client_id and secret are both required.")
    creds = {"client_id": client_id, "secret": secret, "env": env}
    try:
        link_token(creds)                  # cheapest call that checks the keys
    except PlaidError as e:
        sys.exit(f"Plaid rejected the keys: {e}")
    write_private(CREDS, creds)
    print(f"Keys work; saved to {CREDS}. Next: uv run linked-accounts link")


def fetch_positions(creds, items):
    """Holdings for every mapped account of every login that answered.

    Returns (positions by workbook account, accounts refreshed, failures).
    An account whose login failed is not in `refreshed`, so its Holdings
    rows are kept as they are.

    Some institutions (Fidelity's core money market, for one) leave
    uninvested cash out of the holdings list. Whatever part of an account's
    balance the holdings don't account for is added as CASH.

    Unlisted funds (401(k) plan funds and trusts; see GLOSSARY.md) are keyed
    by their name, not by the plan code some institutions put in
    ticker_symbol, and are marked to be priced from Broker Price.
    """
    positions, refreshed, failed = {}, set(), 0
    unlisted_ids = {}          # unlisted key -> {security_id: {accounts}}
    for item in items:
        acct_map = {a["account_id"]: a["workbook_account"]
                    for a in item["accounts"] if a.get("workbook_account")}
        try:
            resp = plaid(creds, "/investments/holdings/get",
                         access_token=item["access_token"])
        except PlaidError as e:
            failed += 1
            hint = (f" — run `relink {item['institution']}`"
                    if e.code == "ITEM_LOGIN_REQUIRED" else "")
            print(f"  {item['institution']}: {e}{hint}", file=sys.stderr)
            continue
        refreshed |= set(acct_map.values())
        secs = {s["security_id"]: s for s in resp["securities"]}
        n, held = 0, {}
        for h in resp["holdings"]:
            acct = acct_map.get(h["account_id"])
            if not acct:
                continue
            held[h["account_id"]] = (held.get(h["account_id"], 0)
                                     + (h.get("institution_value") or 0))
            s = secs.get(h["security_id"], {})
            ticker = s.get("ticker_symbol") or s.get("name") or h["security_id"]
            price, source, price_date = h.get("institution_price"), None, None
            if s.get("is_cash_equivalent") and ticker.startswith("CUR:"):
                ticker = CASH_TICKER
            elif is_unlisted(s):
                ticker = (s.get("name") or "").strip() or h["security_id"]
                source = BROKER
                price_date = h.get("institution_price_as_of")
                if price is None:
                    value, qty = h.get("institution_value"), h["quantity"]
                    if value is not None and qty:
                        price = value / qty
                    else:
                        print(f"  WARNING: {acct}: no price for {ticker}",
                              file=sys.stderr)
                unlisted_ids.setdefault(ticker, {}).setdefault(
                    h["security_id"], set()).add(acct)
            positions.setdefault(acct, []).append({
                "ticker": ticker, "cusip": s.get("cusip") or "",
                "name": s.get("name") or "", "type": s.get("type") or "",
                "quantity": h["quantity"], "price": price,
                "price_source": source,
                "price_date": (date.fromisoformat(price_date)
                               if price_date else None),
                "institution": item["institution"]})
            n += 1
        for a in resp.get("accounts", []):
            acct = acct_map.get(a["account_id"])
            balance = (a.get("balances") or {}).get("current")
            if not acct or balance is None:
                continue
            gap = round(balance - held.get(a["account_id"], 0), 2)
            if gap >= 1:
                positions.setdefault(acct, []).append({
                    "ticker": CASH_TICKER, "cusip": "", "name": "cash",
                    "type": "cash", "quantity": gap, "price": 1,
                    "institution": item["institution"]})
                print(f"  {acct}: ${gap:,.2f} of the balance is not in the "
                      "holdings list; added as CASH")
        ignored = sum(1 for a in item["accounts"]
                      if not a.get("workbook_account"))
        print(f"  {item['institution']}: {n} positions"
              + (f" ({ignored} accounts ignored)" if ignored else ""))
    for key, ids in unlisted_ids.items():
        if len(ids) > 1:
            accts = ", ".join(sorted(set().union(*ids.values())))
            print(f'  WARNING: "{key}" is {len(ids)} different Plaid '
                  f"securities ({accts}); their Holdings rows are merged",
                  file=sys.stderr)
    return positions, refreshed, failed


def update_workbook(path, positions, refreshed, dry_run):
    """Rewrite the Holdings rows of `refreshed` accounts from `positions`.

    Bonds are skipped (the TIPS sheet carries face/coupon/maturity) and only
    cross-checked. Each refreshed account's new rows go where its old rows
    started, so the sheet keeps its order; manual rows are untouched.
    Account names match the Accounts sheet ignoring case, and are written
    in its spelling. Several lots of one fund (e.g. 401(k) contribution
    sources) are merged into one row.
    """
    import openpyxl
    from copy import copy

    require_workbook(path)
    if not dry_run:
        ensure_closed(path, "fetch")
    wb = openpyxl.load_workbook(path)
    ws = wb["Holdings"]
    tips = {(str(r[0]).strip().lower(), r[1])
            for r in wb["TIPS"].iter_rows(min_row=2, values_only=True)
            if r and r[0]}
    stamp = f"Plaid {date.today().isoformat()}"
    key = lambda name: str(name or "").strip().lower()
    spelling = {key(r[0]): r[0] for r in wb["Accounts"].iter_rows(
        min_row=2, values_only=True) if r and r[0]}

    new, names = {}, {}
    for mapped in refreshed:
        acct = spelling.get(key(mapped))
        if acct is None:
            acct = mapped
            print(f"  WARNING: '{mapped}' is not on the Accounts sheet; "
                  "fix it with `map`")
        merged = {}         # ticker -> [quantity, price, source, date]
        for p in positions.get(mapped, []):
            if p["type"] == "fixed income":
                if p["cusip"] and (key(acct), p["cusip"]) not in tips:
                    print(f"  WARNING: {acct} holds bond {p['cusip']} "
                          f"({p['name']}) that is not on the TIPS sheet")
                continue
            m = merged.setdefault(p["ticker"], [0, p["price"],
                                                p.get("price_source"),
                                                p.get("price_date")])
            m[0] += p["quantity"]
        names[key(acct)] = acct
        new[key(acct)] = [(acct, t, round(q, 6), price, stamp, src, pdate)
                          for t, (q, price, src, pdate) in merged.items()]

    # read all 7 columns so hand-entered rows keep Price Source/Price Date
    old = [tuple(r) + (None,) * (7 - len(r))
           for r in ws.iter_rows(min_row=2, max_col=7, values_only=True)
           if any(v not in (None, "") for v in r)]
    out, placed = [], set()
    for r in old:
        k = key(r[0])
        if k in new:
            if k not in placed:
                out.extend(new[k])
                placed.add(k)
        else:
            out.append(r)
    for k in sorted(set(new) - placed):       # newly linked accounts go last
        out.extend(new[k])

    for k in sorted(new):
        before, after = {}, {r[1]: r[2] for r in new[k]}
        for r in old:
            if key(r[0]) == k:
                before[r[1]] = before.get(r[1], 0) + (r[2] or 0)
        changes = [f"{t} {before.get(t, 0):g} -> {after.get(t, 0):g}"
                   for t in sorted(set(before) | set(after))
                   if round(before.get(t, 0), 6) != round(after.get(t, 0), 6)]
        dupes = sum(1 for r in old if key(r[0]) == k) - len(before)
        if dupes:
            changes.append(f"{dupes} duplicate rows merged")
        print(f"  {names[k]}: "
              + ("; ".join(changes) if changes else "no change"))

    if dry_run:
        print("Dry run: workbook not changed.")
        return
    saved = backup(path)

    for col, title in ((4, "Broker Price"), (5, "Updated"),
                       (6, "Price Source"), (7, "Price Date")):
        cell = ws.cell(row=1, column=col, value=title)
        cell._style = copy(ws.cell(row=1, column=1)._style)
    ws.delete_rows(2, ws.max_row)
    for r in out:
        ws.append(list(r))
        if r[6] is not None:
            ws.cell(row=ws.max_row, column=7).number_format = "yyyy-mm-dd"
    wb.save(path)
    print(f"Updated Holdings sheet in {path} (backup: {saved})")


def cmd_fetch(creds, args):
    items = load_items()
    if not items:
        sys.exit("No linked logins. Run `uv run linked-accounts link` first.")
    positions, refreshed, failed = fetch_positions(creds, items)
    if refreshed:
        update_workbook(Path(args.workbook), positions, refreshed,
                        args.dry_run)
    # a failed login leaves that institution's Holdings rows as they were;
    # signal it like fetch_prices does
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="store and check your Plaid API keys")
    sub.add_parser("link", help="link a new institution login")
    sub.add_parser("list", help="show linked logins and account mapping")
    sub.add_parser("map", help="re-map accounts to workbook account names")
    for name, text in (("relink", "repair a login after a password/MFA change"),
                       ("unlink", "revoke a login's token and forget it")):
        p = sub.add_parser(name, help=text)
        p.add_argument("name", help="institution name prefix")
    p = sub.add_parser("fetch", help="update the workbook Holdings sheet")
    p.add_argument("--workbook", default=WORKBOOK)
    p.add_argument("--dry-run", action="store_true",
                   help="show what would change without saving")
    args = ap.parse_args()

    creds = None if args.cmd == "setup" else load_creds()
    try:
        code = globals()[f"cmd_{args.cmd}"](creds, args)
    except PlaidError as e:
        sys.exit(f"Plaid error {e}")
    sys.exit(code or 0)


if __name__ == "__main__":
    main()
