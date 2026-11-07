---
id: 03
title: How is a no-ticker fund identified in Holdings and Assets?
label: wayfinder:grilling
status: open
assignee:
blocked_by: [01, 02]
---

## Question

What value goes in the Ticker column of Holdings, and is used as the Assets key, for a fund with no market ticker? The candidates are Plaid's plan code (`XPLNLS`), the fund name, Plaid's `security_id`, or a user-chosen alias mapped from one of these. Test each against two plans offering "Target Date 2030 Fund" with different underlying holdings, a fund rename, and a plan-code change.
