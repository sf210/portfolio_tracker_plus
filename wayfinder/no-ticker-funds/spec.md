# Spec: unlisted funds, docs, workbook move

Assembled 2026-11-07 from the closed tickets of the map
[Holdings without a market ticker](map.md). Terms are as defined in
`GLOSSARY.md`. Each section names the ticket that holds its reasoning.

Implement in this order: **A** (workbook move), **B** (unlisted funds),
**C** (docs). B builds on A's single path constant, and C describes the
result of both.

---

## A. Workbook move
From [What do docs/ARCHITECTURE.md and CLAUDE.md cover?](07-architecture-doc-scope.md)

1. **Path.**
   - Set `workbook_io.WORKBOOK` to `ROOT / "data" / "portfolio_input.xlsx"`.
   - `fetch_prices.py` (`INPUT_WB`) and `report.py` (the `--workbook`
     default) import `WORKBOOK` instead of building their own path.
   - The lock check in `ensure_closed` follows the new path, so it needs no
     change.
2. **Untrack.**
   - `git rm --cached src/portfolio_input.xlsx`.
   - Move the file with `mv`. The owner does this step, with LibreOffice
     closed.
   - `data/` is already git-ignored.
3. **Example workbook.**
   - Commit `examples/portfolio_input.example.xlsx` with the five sheets
     (Accounts, Holdings, TIPS, Assets, Targets) and their current headers,
     including the two new Holdings columns from B2.
   - Add two or three made-up rows per sheet.
   - Use no real balances or account numbers.
4. **Missing workbook.** If `WORKBOOK` doesn't exist, every command exits
   with a message that tells the owner to copy the example to
   `data/portfolio_input.xlsx`.

## B. Unlisted funds

### B1. Detection and key: `linked_accounts.py`, `fetch_positions`
From [How is a no-ticker fund identified in Holdings and Assets?](03-fund-identity.md)

- **Detection.** A security is **unlisted** when `close_price` is null **or**
  `proxy_security_id` is set. Use no other test. Specifically, don't use a
  null ticker, the ticker's shape, or a missing CUSIP: no security in this
  account has a CUSIP.
- **Key.** For an unlisted security, `ticker = security["name"].strip()`.
  Ignore `ticker_symbol`, because it is a plan code (e.g. `XPLNLS`).
- **Never use** `proxy_security_id` or the proxy security for anything except
  detection. The snapshot shows its matches are wrong.
- **Price.** `price = institution_price`. If that is null, use
  `institution_value / quantity` when both are present and quantity ≠ 0.
  Otherwise use `None` and print a warning naming the account and fund.
- **Price Date.** `price_date = institution_price_as_of`. It may be null.
- **Price Source.** `price_source = "broker"` for unlisted funds, `None`
  otherwise.
- **Same name for different funds.** After all logins are read, warn
  for every key that maps to more than one `security_id`:
  `WARNING: "<name>" is <n> different Plaid securities (<accounts>); their
  Holdings rows are merged`. Warn only; don't rename anything.
- **Listed securities and CASH:** unchanged.

### B2. Holdings sheet: `update_workbook`
From [How are no-ticker funds kept out of the Yahoo lookup and priced from Broker Price?](04-pricing-path.md)

- **New columns:**

  | Col | Header | Written by | Values |
  |---|---|---|---|
  | F | Price Source | `fetch`, or the owner on hand-entered rows | `broker` or blank |
  | G | Price Date | `fetch` | a date, or blank |

  Write the headers the way D and E are written now, copying A1's style.
- **Read all seven columns.** Read old rows with `max_col=7`, padding to 7.
  Today the code reads `max_col=5`, so the new columns would be dropped from
  every row it doesn't refresh.
- **Lot merge** stays keyed by ticker. It carries `price`, `price_source`
  and `price_date` from the first lot, which is correct because all lots of
  one security share them.
- **Change report:** unchanged (shares only).

### B3. Price step: `fetch_prices.py`, `read_inputs`
From [How are no-ticker funds kept out of the Yahoo lookup and priced from Broker Price?](04-pricing-path.md)

- **Read Holdings.** Build the set of keys whose **every** Holdings row has
  Price Source `broker`.
- **Skip those keys** for Yahoo and print
  `<key>: unlisted; priced from Broker Price`.
- **Keep the shape check** (`[\w.^=-]+`) as a fallback for unmarked keys.

### B4. Report: `report.py`
From [How are no-ticker funds kept out of the Yahoo lookup and priced from Broker Price?](04-pricing-path.md)

- **Read Holdings F and G** as `price_source` and `price_date`.
- **Price precedence** in `compute`:
  1. Price Override
  2. for a `broker` row: Broker Price; if missing, warn
     `No Broker Price for <key> (<account>) — holding skipped`
  3. Quote
  4. Broker Price
  5. none: warn and skip, as today
- **Staleness.** For a `broker` row, warn
  `Broker Price for <key> (<account>) is from <date>, <n> days old` when the
  Price Date is more than 5 calendar days before the report date. Warn
  `<key> (<account>) has no Price Date` when it is missing. Warn once per
  key and account.
- **Holdings table.** For a `broker` row, show the price cell as
  `10.54 · broker 11-06` (`MM-DD` of the Price Date), or `10.54 · broker`
  without a date. Other rows are unchanged.

### B5. Classification: `fetch_composition.py`
From [How are no-ticker funds classified, and how do today's manual rows migrate?](05-classification-migration.md)

- **No code change.** These behaviours already exist:
  - A `like TICKER` row takes the comparable fund's look-through.
  - A failed look-through leaves the rows as they are.
  - A `manual` row is never looked up.
  - A new Holdings key gets a row with a blank Class.
- **Precedence to document:** a `manual` Source on *any* row of a key
  outranks `like` on another row. The migration therefore sets Source on
  every row of each fund.

### B6. One-time migration (owner, by hand, before 401k A's first fetch)
From [How are no-ticker funds classified, and how do today's manual rows migrate?](05-classification-migration.md)

1. Close LibreOffice. Do A2 if it hasn't been done.
2. On the Assets sheet:
   - Rename every `US Large Cap Index Fund` row to
     `U.S. Large Cap Stock Index Fund`.
   - Set Source on **every** row of each fund as follows. Leave the existing
     Class rows in place as the fallback.

     | Key | Source |
     |---|---|
     | The Vanguard Target Retire 2070 Trust I | `like VLXVX` |
     | The Vanguard Target Retire 2025 Trust I | `like VTTVX` |
     | Target Date 2030 Fund | `like VTHRX` |
     | U.S. Large Cap Stock Index Fund | `like VOO` |
     | U.S. Core Bond Index | `like BND` |

   - Add `Capital Preservation Fund | Capital Preservation Fund | Cash | 1 |
     | manual`.
3. Run `uv run linked-accounts fetch --dry-run`, then `fetch`. 401k A's
   hand-entered Holdings rows are replaced.
4. Run `uv run fetch-composition --dry-run`, then `fetch-composition`.
5. Run `uv run report`. Check that there are no Unclassified warnings and
   that 401k A's total matches its balance.

### B7. README updates
- **Linked accounts:** describe unlisted funds as keyed by fund name,
  priced from Broker Price, with Price Source and Price Date. Add the rename
  procedure: rename the old Assets rows to the new name. Add the meaning of
  the name-collision warning.
- **Fund look-through:** comparable funds. Explain that `manual` means
  never look up and that it outranks `like`.
- **Paths:** change every `src/portfolio_input.xlsx` to
  `data/portfolio_input.xlsx`, and describe copying the example workbook on
  first use.

## C. Documentation
From [Where do the project docs live?](06-docs-location.md) and [What do docs/ARCHITECTURE.md and CLAUDE.md cover?](07-architecture-doc-scope.md)

1. In `.gitignore`, replace `docs/` with `docs/plaid_master_agreement`.
2. Write `docs/ARCHITECTURE.md`, for someone about to change the code:
   - pipeline order (`update.py`) and what each command reads and writes;
   - a column-ownership table for every sheet: which script writes each
     column, which only reads it;
   - price precedence (B4);
   - safety rules: backup before write, LibreOffice lock, a fetched account
     replaces only its own rows;
   - local state in `config/` and `data/` and what is git-ignored;
   - external services (Plaid, Yahoo, FedInvest, SEC EDGAR), what each
     supplies and how each is known to break.
3. Write `CLAUDE.md` at the root, about 30 lines:
   - pointers to README, GLOSSARY, ARCHITECTURE and `wayfinder/`;
   - run with `uv run …`;
   - hard rules: never print or commit `config/plaid_*.json`; close
     LibreOffice before writes; Plaid production calls hit real accounts;
     `--dry-run` first.
   - It repeats nothing from the other docs.
4. Trim each module docstring to purpose and usage, pointing at
   ARCHITECTURE for file flow. Remove the stale
   `~/finance/planning/.venv` path from `report.py`.
5. `GLOSSARY.md` is done
   ([Which remaining terms does the glossary define, and how?](08-remaining-glossary-terms.md)).
   Keep it in step with any new terms.

## Acceptance checks
- `linked-accounts fetch --dry-run` shows 401k A's three funds under their
  Plaid names, with no plan codes.
- After fetch, Holdings F and G are filled for the six unlisted funds and
  are blank for listed ones. Hand-entered rows keep any F and G values.
- `fetch-prices` prints "unlisted; priced from Broker Price" for the six
  funds and sends none of them to Yahoo.
- The report prices them as `· broker MM-DD` and has no Unclassified or
  stale warnings on a fresh fetch.
- Setting a Price Date back 6 days produces the stale warning.
- `git status` no longer lists the workbook, and `examples/` is committed.

## Not in this spec
See the map's Out of scope section. In particular, removing the workbook
from git history must happen before the first GitHub push.
