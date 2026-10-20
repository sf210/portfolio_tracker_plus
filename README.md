# Allocation portfolio tracker

Fetches current prices and builds a self-contained HTML report of portfolio
allocation. Managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
uv sync          # creates .venv and installs dependencies (openpyxl)
```

uv auto-syncs before every `uv run`, so this step is optional once the
lockfile exists — the first `uv run` will create the environment.

## Running

The one command for a normal refresh — fetches prices, then builds the report:

```bash
uv run update.py            # add --debug to save raw HTTP responses
```

The individual steps, if you need them separately:

```bash
uv run fetch-prices                 # ETF/fund + TIPS prices -> data/
uv run report                       # -> output/portfolio_report.html

# equivalent, running the source files directly:
uv run src/fetch_prices.py --debug
uv run src/report.py -o output/portfolio_report.html
```

## Linked accounts (Plaid)

`src/linked_accounts.py` pulls holdings directly from Fidelity, Vanguard and
Empower through Plaid's read-only Investments product. You log in inside
Plaid Link in your browser; only the access token is stored, in
`config/plaid_items.json` (mode 600, git-ignored).

One-time setup:

1. Sign up at <https://dashboard.plaid.com/signup> and choose **Personal use**
   (free Trial plan, up to 10 linked logins).
2. Copy the keys from *Developers > Keys* into `config/plaid_credentials.json`:
   `{"client_id": "...", "secret": "...", "env": "production"}`
   (use the sandbox secret with `"env": "sandbox"` to try it with the test
   login `user_good` / `pass_good`).
3. If Fidelity is not offered in Link, request it on the dashboard's
   *OAuth Institutions* page.

```bash
uv run src/linked_accounts.py link       # once per institution login
uv run src/linked_accounts.py list       # check the account mapping
uv run src/linked_accounts.py fetch      # -> data/holdings_linked.csv
```

During `link` each Plaid account is mapped to a name on the workbook's
Accounts sheet (`-` ignores it). `update.py` runs `fetch` automatically once
a login exists. In `report.py`, an account that appears in
`data/holdings_linked.csv` takes its holdings from there instead of the
Holdings sheet. Bonds always come from the TIPS sheet, and linked bond
CUSIPs missing from it trigger a warning. Uninvested cash comes through as
ticker `CASH`, so add a `CASH` row to the Assets sheet (class Cash, price
override 1). Funds with no ticker, such as 401(k) trust funds, use the
fund's name as the ticker and the price the broker reports.

If a login expires or MFA changes, `fetch` prints
`ITEM_LOGIN_REQUIRED — run relink <name>`. Run that command and log in
again. `unlink <name>` revokes the token at Plaid.

## Adding a dependency

```bash
uv add <package>     # updates pyproject.toml + uv.lock, installs it
```
