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
                          (or set PLAID_CLIENT_ID / PLAID_SECRET / PLAID_ENV)
  plaid_items.json        linked logins: access tokens + account mapping

Writes:
  data/holdings_linked.csv   read by report.py; replaces the Holdings-sheet
                             rows of every account that appears in it

Usage:
  uv run src/linked_accounts.py link          # opens browser, log in, map accounts
  uv run src/linked_accounts.py list          # show linked logins/accounts
  uv run src/linked_accounts.py map           # re-map Plaid accounts to workbook names
  uv run src/linked_accounts.py relink NAME   # repair a login (password/MFA changed)
  uv run src/linked_accounts.py unlink NAME   # revoke the token at Plaid and forget it
  uv run src/linked_accounts.py fetch         # -> data/holdings_linked.csv

NAME is the institution name as shown by `list` (case-insensitive prefix).
"""

import argparse
import csv
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

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
CREDS = CONFIG / "plaid_credentials.json"
ITEMS = CONFIG / "plaid_items.json"
WORKBOOK = ROOT / "src" / "portfolio_input.xlsx"
OUT = ROOT / "data" / "holdings_linked.csv"

HOSTS = {"production": "https://production.plaid.com",
         "sandbox": "https://sandbox.plaid.com"}
LINK_JS = "https://cdn.plaid.com/link/v2/stable/link-initialize.js"
CASH_TICKER = "CASH"     # Plaid reports uninvested cash as ticker CUR:USD


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
        sys.exit(f"No Plaid credentials. Create {CREDS} with client_id, secret "
                 "and env (from dashboard.plaid.com > Developers > Keys).")
    if c["env"] not in HOSTS:
        sys.exit(f"env must be one of {', '.join(HOSTS)}, not {c['env']!r}")
    return c


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


def cmd_fetch(creds, args):
    items = load_items()
    if not items:
        sys.exit("No linked logins. Run `link` first.")
    rows, failed = [], 0
    for item in items:
        acct_map = {a["account_id"]: a.get("workbook_account")
                    for a in item["accounts"]}
        try:
            resp = plaid(creds, "/investments/holdings/get",
                         access_token=item["access_token"])
        except PlaidError as e:
            failed += 1
            hint = (f" — run `relink {item['institution']}`"
                    if e.code == "ITEM_LOGIN_REQUIRED" else "")
            print(f"  {item['institution']}: {e}{hint}", file=sys.stderr)
            continue
        secs = {s["security_id"]: s for s in resp["securities"]}
        n = 0
        for h in resp["holdings"]:
            acct = acct_map.get(h["account_id"])
            if not acct:
                continue
            s = secs.get(h["security_id"], {})
            ticker = s.get("ticker_symbol") or s.get("name") or h["security_id"]
            if s.get("is_cash_equivalent") and ticker.startswith("CUR:"):
                ticker = CASH_TICKER
            rows.append({"account": acct, "ticker": ticker,
                         "cusip": s.get("cusip") or "",
                         "name": s.get("name") or "",
                         "type": s.get("type") or "",
                         "quantity": h["quantity"],
                         "price": h.get("institution_price"),
                         "value": h.get("institution_value"),
                         "price_asof": h.get("institution_price_as_of") or "",
                         "institution": item["institution"]})
            n += 1
        unmapped = sum(1 for a in item["accounts"]
                       if not a.get("workbook_account"))
        print(f"  {item['institution']}: {n} positions"
              + (f" ({unmapped} accounts ignored)" if unmapped else ""))

    out = Path(args.output)
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account", "ticker", "cusip", "name",
                                          "type", "quantity", "price", "value",
                                          "price_asof", "institution"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {out} ({len(rows)} rows)")
    # a failed login leaves that institution out of the CSV, so report.py
    # falls back to the workbook for its accounts; signal it like fetch_prices
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("link", help="link a new institution login")
    sub.add_parser("list", help="show linked logins and account mapping")
    sub.add_parser("map", help="re-map accounts to workbook account names")
    for name in ("relink", "unlink"):
        p = sub.add_parser(name)
        p.add_argument("name", help="institution name prefix")
    p = sub.add_parser("fetch", help="download holdings to CSV")
    p.add_argument("-o", "--output", default=OUT)
    args = ap.parse_args()

    creds = load_creds()
    try:
        code = globals()[f"cmd_{args.cmd}"](creds, args)
    except PlaidError as e:
        sys.exit(f"Plaid error {e}")
    sys.exit(code or 0)


if __name__ == "__main__":
    main()
