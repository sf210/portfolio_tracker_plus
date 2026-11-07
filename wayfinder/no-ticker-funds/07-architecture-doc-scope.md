---
id: 07
title: What do docs/ARCHITECTURE.md and CLAUDE.md cover?
label: wayfinder:grilling
status: closed
assignee: claude
blocked_by: []
---

## Question

What goes in `docs/ARCHITECTURE.md`, and how deep? Candidates: the pipeline (`linked-accounts fetch` → `fetch-prices` → `fetch-composition` → `report`), the workbook as the hub with each script's reads and writes per sheet and column, backups and the LibreOffice lock, the price precedence, and where credentials and cached data live. What goes in the short `CLAUDE.md`, and what should it leave to the README, GLOSSARY and ARCHITECTURE?

## Resolution

Decided with the owner, 2026-11-07.

1. **`docs/ARCHITECTURE.md`** is for someone about to change the code. It
   works at the level of modules and data, not functions, and covers:
   - **Pipeline:** the order in `update.py`, and what each command
     (`linked-accounts fetch`, `fetch-prices`, `fetch-composition`, `report`)
     reads and writes.
   - **Workbook as the hub:** a column-ownership table for each sheet
     (Accounts, Holdings, TIPS, Assets, Targets) showing which script writes
     each column and which only reads it.
   - **Price precedence:** Price Override → Broker Price for `broker` rows →
     Quote → Broker Price.
   - **Safety rules:** a backup before every write; no write while the
     LibreOffice lock exists; a fetched account replaces only its own rows.
   - **Local state:** what's in `config/` and `data/`, and what is
     git-ignored.
   - **External services:** Plaid, Yahoo, FedInvest and SEC EDGAR, with what
     each supplies and how each is known to break.
2. **`CLAUDE.md`** is about 30 lines:
   - pointers to README, GLOSSARY, ARCHITECTURE and `wayfinder/`;
   - run everything with `uv run …`;
   - hard rules: never print or commit `config/plaid_*.json`; close LibreOffice
     before any write; Plaid production calls hit real accounts; `--dry-run`
     first.
   - It repeats nothing that's in the other docs.
3. **Module docstrings** are trimmed to purpose and usage, pointing at
   ARCHITECTURE for file flow. The detailed "Reads:/Writes:" lists are what
   drifted; for example, `report.py` still names the old venv path.
4. **Workbook location** (raised by the owner):
   - The workbook moves to `data/portfolio_input.xlsx` and stops being tracked
     in git. Its history from then on is `data/backups/`.
   - Every script takes the path from `workbook_io.WORKBOOK`. Today
     `fetch_prices.py` (`INPUT_WB`) and `report.py` (a `--workbook` default)
     each hard-code `src/`.
   - A committed example workbook, `examples/portfolio_input.example.xlsx`,
     has the five sheets, their headers and a few made-up rows.
   - Removing the workbook from past git history is out of scope here. It is
     a prerequisite for the first GitHub push and is listed on the map.
