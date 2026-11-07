# Architecture

For someone about to change the code. [README.md](../README.md) covers how to
use the tracker, and [GLOSSARY.md](../GLOSSARY.md) defines the terms used
here (Holding, Unlisted fund, Broker Price, Quote, …).

## Pipeline

`uv run update.py` runs three steps in order. Each step is a separate command
and a separate process:

| Step | Command | Reads | Writes |
|---|---|---|---|
| 1 | `linked-accounts fetch` (only if `config/plaid_items.json` exists) | Plaid; workbook Accounts, Holdings, TIPS | workbook **Holdings** |
| 2 | `fetch-prices` | workbook Assets, Holdings, TIPS; Yahoo, FedInvest, TreasuryDirect, BLS/FRED | `data/prices.csv`, `data/tips_prices.csv`, `data/tips_ref.csv` |
| 3 | `report` | workbook (all sheets), `data/prices.csv`, `data/tips_prices.csv` | `output/portfolio_report.html` |

`update.py --workbook PATH` runs the same pipeline on another workbook
(the example, say). It skips step 1, and `workbook_io.outputs_for` gives
that workbook its own price files, `data/<stem>/prices.csv` and
`tips_prices.csv`, and report, `output/portfolio_report.<name>.html`. The
paths in the table are the real workbook's.

If step 1 or 2 fails partway, `update.py` warns and carries on. The report is
built from whatever data is there.

`fetch-composition` is not part of `update.py`. Run it after a fetch adds a
new Holdings ticker, and about once a quarter as new N-PORT filings appear.
It reads Assets and Holdings, plus SEC EDGAR, and rewrites the **Assets**
sheet.

Data flows one way: from the institutions and public sources, into the
workbook and `data/`, and then into the report. No step reads the report.

## The workbook is the hub

`data/portfolio_input.xlsx` is the only shared state. The owner edits it in
LibreOffice. Three commands write to it, and each owns specific sheets. The
path is defined once, as `workbook_io.WORKBOOK`.

| Sheet | Column | Written by | Read by |
|---|---|---|---|
| **Accounts** | Name, Type, Institution, Owner, Tax Type | owner | `report` (all); `linked-accounts` (Name, for mapping and spelling) |
| **Holdings** | A Account, B Ticker, C Shares | `fetch` for linked accounts; owner for the rest | `report`; `fetch-composition` (B); `fetch-prices` (B) |
| | D Broker Price | `fetch`; owner | `report` |
| | E Updated | `fetch` (`Plaid YYYY-MM-DD`); owner | nobody, it's for the owner |
| | F Price Source | `fetch` (`broker` for unlisted funds); owner | `fetch-prices`, `report` |
| | G Price Date | `fetch`; owner | `report` (staleness) |
| **TIPS** | Account, CUSIP, Face, Coupon, Maturity, Description, Cost Basis | owner; `import-tipsladder` replaces one Account's rows | `report` (all); `fetch-prices` (CUSIP, Maturity); `fetch` (Account and CUSIP cross-check) |
| **Assets** | A Ticker, B Name, C Class, D Class Pct, E Price Override, F Source | `fetch-composition` rewrites the sheet, keeping `manual` rows and Price Overrides; owner | `report` (A–E); `fetch-prices` (A, E) |
| **Targets** | Class, Category, Parent, Target, Threshold | owner | `report` |

The joins:
- **Holdings.Ticker = Assets.Ticker** gives a Holding its Classes and any
  Price Override. An unlisted fund's key is its fund name.
- **Holdings.Account = Accounts.Name** gives tax type and owner. The match
  ignores case in `fetch` and is exact in `report`.
- **Assets.Class = Targets.Class** gives Category and Parent. A Class with
  no Targets row rolls up to "Other".

Bonds are never on Holdings. `fetch` skips Plaid's fixed-income lots, and the
TIPS sheet is the record of them.

## Price precedence

`report.compute` prices each Holding by taking the first of these that
applies:

1. **Price Override** (Assets column E).
2. For a **`broker`** row (Holdings F): **Broker Price**, and never a Quote.
   If it's missing, the holding is skipped with a warning. A Price Date
   older than 5 days, or missing, also gives a warning.
3. **Quote** from `data/prices.csv`.
4. **Broker Price**, for unmarked rows that have no Quote.
5. Otherwise the holding is skipped with a warning.

`fetch-prices` doesn't send Yahoo a key whose Holdings rows are all
`broker`. As a fallback for unmarked rows, it also skips any key that
doesn't look like a symbol (for example, one containing a space).

TIPS value = face × index ratio × clean price / 100. The index ratio is Ref
CPI at settlement divided by Ref CPI on the dated date.

## How unlisted funds are handled

All of this happens in `linked_accounts.fetch_positions`:
- **Detection:** `is_unlisted` is true when Plaid's `close_price` is null
  or `proxy_security_id` is set.
- **Key:** the security's trimmed `name`. The `ticker_symbol` (a plan code)
  is ignored, and so is the proxy security, because its matches are wrong.
- **Fields written:** Price Source is `broker`; Price Date is
  `institution_price_as_of`. If `institution_price` is null, the price is
  `institution_value / quantity`.
- **Collisions:** a warning if one name is several Plaid securities in a
  single fetch.
- **Classification:** done in `fetch-composition` through a comparable
  fund (`like TICKER`). The reasoning is in
  [wayfinder/no-ticker-funds](../wayfinder/no-ticker-funds/map.md).

## Safety rules

Every writer to the workbook follows these rules:

- **The LibreOffice lock.** `workbook_io.ensure_closed` refuses to write
  while `data/.~lock.portfolio_input.xlsx#` exists. LibreOffice would
  overwrite the change when it saves.
- **Backup first.** `workbook_io.backup` copies the workbook to
  `data/backups/portfolio_input_YYYYMMDD-HHMMSS.xlsx` before every write.
  These copies are the workbook's history, because git doesn't track it.
- **Only touch your own rows.**
  - `fetch` replaces the Holdings rows of the accounts it refreshed, and
    keeps their position in the sheet.
  - Accounts that weren't fetched, and logins that failed, keep their rows
    exactly as they were, all seven columns.
  - `fetch-composition` leaves `manual` rows alone. `manual` on any row of
    a ticker outranks `like` on another row.
- **`--dry-run`** on `fetch`, `fetch-composition` and `import-tipsladder` prints the changes
  without writing anything.
- **A missing workbook** stops the command with a hint to copy
  `examples/portfolio_input.example.xlsx`. The exception is
  `linked-accounts link` and `map`, which still run, without the
  account-name hints.

## Local state

| Path | Contents | Git |
|---|---|---|
| `data/portfolio_input.xlsx` | the workbook | ignored (holds balances) |
| `data/backups/` | a workbook copy before each write | ignored |
| `data/prices.csv`, `data/tips_prices.csv` | Quotes and TIPS prices from the last `fetch-prices` | ignored |
| `data/tips_ref.csv` | Ref CPI on each TIPS dated date. It never changes, so it is cached. | ignored |
| `data/<workbook stem>/` | prices for a workbook other than the real one | ignored |
| `data/nport/` | SEC filings and ticker lists | ignored |
| `data/plaid_snapshots/` | raw Plaid holdings saved for analysis | ignored |
| `config/plaid_credentials.json` | Plaid client id, secret and environment (mode 600) | ignored |
| `config/plaid_items.json` | Plaid access tokens and account mapping (mode 600) | ignored |
| `config/sec_contact.txt` | name and email sent to the SEC | ignored |
| `output/portfolio_report*.html` | the report; `.example` etc. for other workbooks | ignored |
| `examples/portfolio_input.example.xlsx` | made-up starter workbook | committed |

## External services

| Service | Used by | Supplies | Known ways it breaks |
|---|---|---|---|
| **Plaid** Investments (`/investments/holdings/get`) | `linked-accounts` | Holdings, lots, Broker Prices, balances | `ITEM_LOGIN_REQUIRED` after a password or MFA change, so run `relink`. Some institutions leave cash out of holdings; `fetch` adds the gap as `CASH`. Plan funds come with plan codes as tickers and with wrong proxy securities. No CUSIPs without a license. |
| **Yahoo Finance** chart API | `fetch-prices` | Quotes | Unofficial and keyless. It can rate-limit or change shape. A missing quote falls back to Broker Price. |
| **TreasuryDirect FedInvest** | `fetch-prices` | TIPS clean prices by CUSIP | Needs a session and a CSRF token for each form. The site changed this flow in 2026 (commit `61f980b`). No file on weekends or holidays, so it walks back up to 7 days. |
| **TreasuryDirect** securities API | `fetch-prices`, `import-tipsladder` | Ref CPI on the dated date; coupons | Renamed `refCpiOnDatedDate` to `referenceCpiOnOriginalDatedDate` in 2026; both are read. Results are cached in `tips_ref.csv`. |
| **BLS** API v2, with **FRED** CSV as fallback | `fetch-prices` | CPI-U NSA for the current Ref CPI | BLS can stall, so it is retried. FRED sits behind Akamai and is unreliable. |
| **SEC EDGAR** | `fetch-composition` | N-PORT and N-MFP filings, and the fund ticker list | Requires a User-Agent with contact details. Filings arrive 2–4 months after quarter end. Trusts and plan funds don't file at all, hence comparable funds. |

## Modules

| Module | Role |
|---|---|
| `update.py` | runs the pipeline |
| `src/workbook_io.py` | workbook path, per-workbook output paths, lock check, backup, missing-workbook hint |
| `src/linked_accounts.py` | Plaid Link on localhost, account mapping, `fetch` into Holdings |
| `src/fetch_prices.py` | Quotes and TIPS prices into `data/` |
| `src/fetch_composition.py` | N-PORT look-through into Assets |
| `src/report.py` | valuation, roll-up and the self-contained HTML report |
| `src/tipsladder_import.py` | tipsladder.com CSV into one Account's TIPS rows (coupons from TreasuryDirect) |
