# Allocation portfolio tracker

Fetches current prices and builds a self-contained HTML report of portfolio
allocation. Managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
uv sync          # creates .venv and installs dependencies (openpyxl)
```

uv auto-syncs before every `uv run`, so this step is optional once the
lockfile exists — the first `uv run` will create the environment.

The workbook lives at `data/portfolio_input.xlsx`. It is git-ignored because it
holds your balances. On a fresh clone, start from the example and fill in your
own accounts in LibreOffice:

```bash
cp examples/portfolio_input.example.xlsx data/portfolio_input.xlsx
```

## Running

The one command for a normal refresh — refreshes linked holdings (if any),
fetches prices, then builds the report:

```bash
uv run update.py            # add --debug to save raw HTTP responses
```

The individual steps, if you need them separately:

```bash
uv run fetch-composition            # fund asset-class splits -> Assets sheet (quarterly)
uv run fetch-prices                 # ETF/fund + TIPS prices -> data/
uv run report                       # -> output/portfolio_report.html

# equivalent, running the source files directly:
uv run src/fetch_prices.py --debug
uv run src/report.py -o output/portfolio_report.html
```

## Linked accounts (Plaid)

`linked-accounts` refreshes the **Holdings** sheet of
`data/portfolio_input.xlsx` straight from Fidelity, Vanguard and Empower,
using Plaid's read-only Investments product. You type your brokerage
password into Plaid's login window, never into this program; what gets
stored locally is a read-only access token, in `config/plaid_items.json`
(mode 600, git-ignored).

Accounts you don't link keep the Holdings rows you enter by hand. Bonds
always come from the TIPS sheet.

### One-time setup

**1. Create a Plaid account.** Go to <https://dashboard.plaid.com/signup>
and choose **Personal use**. That's the free Trial plan, which allows up to
10 linked logins.

**2. Find your keys.** In the dashboard open **Developers → Keys**. You
need the `client_id` and a secret. Plaid shows separate secrets for
Sandbox and Production:

- **Sandbox** uses fake banks. It's useful for a first dry run with the
  test login `user_good` / `pass_good`.
- **Production** connects to your real accounts.

**3. Save the keys:**

```bash
uv run linked-accounts setup
```

Paste the `client_id`, type `production` or `sandbox`, then paste the
matching secret (it is not shown as you paste). `setup` checks the keys
with Plaid before saving them to `config/plaid_credentials.json`. Run it
again to switch between sandbox and production.

**4. Check the Accounts sheet.** Every account you link must map to a
**Name** on the Accounts sheet, such as `IRA`, `Roth` or `Brokerage`. Add
any missing rows in LibreOffice first.

### Link each institution (once per login)

```bash
uv run linked-accounts link
```

1. A browser tab opens on `http://127.0.0.1:…` and Plaid's window appears.
2. Search for the institution (Fidelity, Vanguard or Empower) and log in.
   This includes any MFA code. Fidelity, and some Vanguard logins, open
   the institution's own site in a pop-up, so allow pop-ups for
   127.0.0.1.
3. Pick the accounts to share and finish. The tab then says "Account
   linked" and you can close it.
4. Back in the terminal, give each account its Accounts-sheet name:

   ```
   Linked Fidelity (2 accounts).

   Fidelity: map each account to a workbook account name (IRA, Roth, Brokerage).
   Press Enter to keep the current value, '-' to ignore the account.
     Individual (brokerage, …1234) [ignored]: Brokerage
     Health Savings Account (hsa, …5678) [ignored]: -
   ```

Repeat `link` for each institution, and for each separate login at the
same institution. `uv run linked-accounts list` shows what is linked and
mapped. `uv run linked-accounts map` changes the names later.

### Refreshing holdings

Close the workbook in LibreOffice first, because `fetch` won't write
while it is open. Then preview the changes:

```bash
uv run linked-accounts fetch --dry-run
```

This shows per-account changes, e.g. `Brokerage: VT 1000 -> 1010.5`,
without saving anything. To write them:

```bash
uv run linked-accounts fetch
```

You can instead run `uv run update.py`, which runs `fetch` automatically
once a login is linked, then fetches prices and builds the report.

What `fetch` does to the Holdings sheet:

- For every account Plaid refreshed, its rows are replaced by the
  current positions. Those rows also get a **Broker Price** and an
  **Updated** (`Plaid YYYY-MM-DD`) value.
- Rows for unlinked accounts, and for accounts whose login failed, are
  left exactly as they were.
- The previous workbook is copied to
  `data/backups/portfolio_input_YYYYMMDD-HHMMSS.xlsx` first.

After the first fetch, run `uv run fetch-composition` (see
[Fund look-through](#fund-look-through-sec-n-port)). It adds an Assets row
for every new Holdings ticker:

- **Cash.** Uninvested cash comes through as ticker `CASH`. It is added
  as class Cash with price override 1.
- **Funds with no ticker,** such as 401(k) trust funds at Empower. These
  use the fund's name as the ticker, and their value comes from Broker
  Price. They are added with Class blank; fill it in, or set Source to
  `like TICKER`.
- **Bonds.** Bond positions stay on the TIPS sheet. `fetch` warns if a
  linked bond's CUSIP is missing from it.

### When something goes wrong

| Message | Fix |
| --- | --- |
| `ITEM_LOGIN_REQUIRED — run relink Fidelity` | Your password or MFA changed, or the login expired. Run `uv run linked-accounts relink Fidelity` and log in again. |
| `…is open in LibreOffice` | Close the workbook (or delete a stale `data/.~lock.portfolio_input.xlsx#`). |
| Institution not offered in Plaid's window | In the dashboard, request it under **OAuth Institutions**. |
| `No Plaid credentials yet` | Run `uv run linked-accounts setup`. |

To stop sharing, run `uv run linked-accounts unlink Fidelity`. This
revokes the token at Plaid and removes it locally.

## Fund look-through (SEC N-PORT)

`fetch-composition` fills the **Assets** sheet with each fund's actual
asset-class split. It reads the fund's latest quarterly SEC N-PORT
filing, which lists every holding with its type and country:

- **Stocks** become U.S. Total Mkt, Intl Total Mkt or Emerging Mkt,
  according to each company's country. Hong Kong counts as emerging.
- **Bonds** become U.S. Bonds or Intl Bonds. Inflation-indexed Treasuries
  become TIPS.
- **Cash** includes cash vehicles, after subtracting cash collateral from
  securities lending.
- **Funds that hold other funds** (target-date funds, for example) are
  looked through to the underlying funds' own filings.

It covers every ticker on the Assets sheet. It also adds rows for every
Holdings ticker that isn't on Assets yet:

- SEC-registered funds get their split from the filing.
- Money market funds get Cash 100%.
- `CASH` gets Cash with price override 1.
- Anything else, such as a 401(k) trust, gets a row with the Class left
  blank. `report.py` warns about it until you fill in Class and Class Pct
  or set Source to `like TICKER`.

```bash
uv run fetch-composition --dry-run     # show the changes
uv run fetch-composition               # write them (close LibreOffice first)
uv run fetch-composition VT VTHRX      # only these tickers
```

The first run asks for a name and email, which is sent with each SEC
request because the SEC requires it. Use any address you're willing to
give the SEC. It is saved in `config/sec_contact.txt` (git-ignored), or
you can set `SEC_USER_AGENT` instead. Downloaded filings are cached in
`data/nport/`. Filings come out quarterly, about 2–4 months after the
period ends, so running this once a quarter is enough.

The **Source** column (F) shows where each row came from:

| Source | Meaning |
| --- | --- |
| `N-PORT 2026-06-30` | Filled from the filing for that date. It is replaced on the next run. |
| `manual` | Left alone. On the first run, rows that use a class a filing can't determine (small/mid cap, REITs, ...) are marked manual. |
| `like VTTVX` | Use another fund's split. This is for 401(k) collective trusts, which don't file with the SEC. Add a row with the trust's exact ticker or name and this Source, and leave Class blank. |
| `N-MFP 2026-10-07` | A money market fund, which files N-MFP instead of N-PORT. It is set to Cash 100%. |
| (blank) | A ticker the SEC doesn't list. It is left as you entered it. |

Like `linked-accounts fetch`, it backs up the workbook to `data/backups/`
first, and it won't write while LibreOffice has the file open.

## Adding a dependency

```bash
uv add <package>     # updates pyproject.toml + uv.lock, installs it
```
