---
id: 09
title: Assemble the implementation spec for unlisted funds
label: wayfinder:task
status: closed
assignee: claude
blocked_by: []
---

## Question

Collect the decisions from the closed fund-identity, pricing and classification tickets into one implementation spec. It covers: changes to `linked_accounts.py`, `fetch_prices.py`, `fetch_composition.py` and `report.py`; the new Holdings columns; warnings; README updates; and the one-time migration checklist. Also include the workbook move to `data/`, the single `WORKBOOK` constant and the example workbook, all from the architecture-doc ticket. Link the spec from the map. AFK; it decides nothing new. Raise any contradiction it finds as a new ticket.

## Resolution

Done 2026-11-07: [spec.md](spec.md). The spec decides nothing new, and no
contradictions between tickets turned up. Checking it against the code
surfaced two implementation details, which the spec now covers:
- `update_workbook` reads only columns A–E of existing Holdings rows, so it
  would drop the new Price Source and Price Date. The fix is to read seven
  columns.
- In `fetch-composition`, `manual` on any Assets row of a key outranks
  `like` on another row. The migration therefore sets Source on every row.
