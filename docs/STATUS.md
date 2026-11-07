# Status and handoff

For an agent picking this project up cold. It records where the work stands
and what isn't obvious from the code. How the system works is in
`ARCHITECTURE.md`, usage is in `README.md`, and terms are in
`../GLOSSARY.md`. Read those for anything not covered here. Last updated
2026-11-07.

## Where things stand

All of this is done, merged to `master` and pushed to
`github.com/sf210/portfolio_tracker_plus` (public):

- **Unlisted funds** (401(k) plan funds, collective trusts):
  - **What they are:** detected from Plaid by `close_price` null or
    `proxy_security_id` set.
  - **Key and price:** keyed by fund name and priced from Broker Price,
    with Price Source `broker` and a Price Date (Holdings F and G).
  - **Classification:** through a comparable fund (`like TICKER` in the
    Assets Source).
  - **Planning record:** `wayfinder/no-ticker-funds/`, a closed map with
    its spec.
  - **Owner's one-time migration:** done and verified.
- **Workbook location:** the workbook lives at `data/portfolio_input.xlsx`
  and is git-ignored. `examples/portfolio_input.example.xlsx` is the
  made-up starter workbook.
- **Docs:** `docs/ARCHITECTURE.md`, `CLAUDE.md` and `GLOSSARY.md`.
- **`import-tipsladder`:** loads a tipsladder.com CSV into one Account's
  TIPS rows. Coupons come from TreasuryDirect, and the ladder's Years
  Funded goes into TIPS column H.
- **`--workbook PATH` on `update.py` and `fetch-prices`:**
  - **Purpose:** runs the pipeline on another workbook, such as the
    example.
  - **What's skipped:** Plaid.
  - **Outputs:** that workbook's prices go to `data/<stem>/` and its
    report to `output/portfolio_report.<name>.html` (see
    `workbook_io.outputs_for`).
  - **Running the example:**
    `uv run update.py --workbook examples/portfolio_input.example.xlsx`.
- **Example workbook:**
  - **Holdings:** VT, BND, a Target Date 2035 Fund at a broker price, and
    a 37-bond TIPS ladder from `examples/tipsladder.csv` (built for
    $20k/yr of real cash flow).
  - **Expected warning:** the Target Date 2035 Fund's Price Date is
    2026-01-02, so its report shows one stale-price warning.

## Decisions an agent would otherwise redo

- **TIPS cash flows are held to maturity, with a trailing 5-year average
  line.**
  - **What was tried:** a "planned spending" view built from Years
    Funded. It levelled the gap years by carrying cash forward and
    estimating early sales.
  - **Why it was removed:** the owner prefers the 5-year average, as
    what the proceeds make available.
  - **Years Funded now:** still recorded in TIPS column H, but the report
    doesn't read it. Don't re-add the plan unless asked.
  - **Where the old code is:** git history, commit "Report: planned TIPS
    spending from Years Funded".
- **Report vs tipsladder.com:** the report matches tipsladder.com's
  schedule (`examples/tips_cashflow.csv`) within about $4/yr, except in
  2036–2040. There tipsladder.com carries the 2036 surplus forward and
  sells part of the 2040 bond in the gap years 2037–2039. That
  difference is expected, not a bug.
- **Classification precedence:** `manual` on any row of a ticker outranks
  `like` on another row. A failed `like` look-through keeps the
  hand-entered split as the fallback.
- **Plaid proxy securities:** never use them for pricing or
  classification. They are wrong matches.
- **TreasuryDirect renamed `refCpiOnDatedDate`** to
  `referenceCpiOnOriginalDatedDate` in 2026. `fetch_prices` reads both.
  `data/tips_ref.csv` caches the values and is shared by all workbooks.

## Privacy: the repo is public

- **What was scrubbed:** before the first push, the history was rewritten
  (`git filter-branch`) to remove:
  - the old workbook;
  - balances and account owners' names;
  - employer names and plan codes;
  - a personal email.
  The 401(k)s are called `401k A/B/C` in the wayfinder notes. The plan
  codes there (`XPLNLS` etc.) are made up.
- **Commit identity:** all commits are by `sf210` with the GitHub noreply
  email, and the repo's local git config sets both. Don't commit under
  another identity.
- **What still must never be committed:**
  - real figures, names or account numbers, in files or in commit
    messages;
  - anything from `config/`, `data/` or `output/`.

  Use made-up figures in examples. The history is published now, so any
  leak would need a rewrite and a force-push.

## Workflow

- **Running:** `uv run …` only. Don't install packages; ask the owner.
- **Landing work:**
  - Work on a branch, commit with a descriptive body, `git merge --no-ff`
    into `master`, delete the branch, then `git push`.
  - The owner's `ship` skill does this cycle.
  - The owner usually asks before commits and pushes.
- **Plaid:** in production, and reads the owner's real accounts. Use
  read-only calls and `--dry-run` first. Never write the workbook while
  the LibreOffice lock exists.
- **Owner's style for replies:** concise, no praise.

## Open threads and ideas

- **Possible separate project:** combine this tracker with the owner's
  annuity / withdrawal simulator (`~/finance/planning/annuity`, a
  separate repo). It was ruled out of scope for the unlisted-funds map and
  hasn't been started.
- **Snapshot ticket:** `wayfinder/no-ticker-funds/02-plaid-holdings-snapshot.md`
  still shows per-share prices from 2026-11-06 and a partial Plaid
  security ID. The owner chose to keep them.
- **Fund renames:** if an institution renames an unlisted fund, the README
  has the manual fix. Nothing automates it.
- **Fixed-income lots:** `fetch` doesn't import Plaid's fixed-income lots.
  TIPS come only from the TIPS sheet, entered by hand or through
  `import-tipsladder`.
