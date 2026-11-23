# CLAUDE.md

Portfolio allocation tracker. Holdings come from Plaid and from hand entry
into a LibreOffice workbook. Prices come from public sources. The output is
an HTML allocation report.

## Read first
- `docs/STATUS.md`: where the work stands, settled decisions, open threads.
  Start here when resuming.
- `README.md`: how to use it (setup, commands, linked accounts, look-through).
- `GLOSSARY.md`: the domain terms. Use them, and avoid the words it lists.
- `docs/ARCHITECTURE.md`: pipeline, which script owns which workbook column,
  price precedence, safety rules, external services.
- `wayfinder/`: planning maps and their decisions. A decision lives in its
  ticket. Local only: git-ignored, so it isn't in the repo.
- `docs/adr/`: decision records, if there are any.

## Running
- Always use `uv run <command>` (`update.py`, `linked-accounts`,
  `fetch-prices`, `fetch-composition`, `report`, `import-tipsladder`).
  Don't use another venv, and don't install packages; ask the owner to.
- The workbook is `data/portfolio_input.xlsx`. It is git-ignored and holds
  real balances. Test against a copy, or against
  `examples/portfolio_input.example.xlsx`.

## Hard rules
- Never print, log or commit anything from `config/plaid_*.json`. Never
  commit `config/`, `data/` or `output/`.
- Plaid is in **production**, so calls read the owner's real accounts. Run
  read-only calls only, and use `--dry-run` first on any command that writes.
- Don't write the workbook while `data/.~lock.portfolio_input.xlsx#` exists.
  Writers must call `workbook_io.ensure_closed` and `backup` first.
- Bonds live on the TIPS sheet, never on Holdings.
- Don't use Plaid's `proxy_security_id` security for pricing or
  classification. Its matches are wrong.
- Keep balances, account owners' names and employer names out of
  committed files and commit messages. Use made-up figures in examples.
