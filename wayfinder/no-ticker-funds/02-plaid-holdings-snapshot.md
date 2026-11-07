---
id: 02
title: Snapshot raw Plaid holdings for every linked login
label: wayfinder:task
status: open
assignee:
blocked_by: []
---

## Question

Save the raw `/investments/holdings/get` response for each linked login to a git-ignored file under `data/` (tokens left out). List every security that has no CUSIP or whose ticker isn't a market symbol, with all of its fields, so the identification and pricing rules can be checked against real data.
