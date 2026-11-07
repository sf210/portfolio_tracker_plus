---
id: 08
title: Which remaining terms does the glossary define, and how?
label: wayfinder:grilling
status: closed
assignee: claude
blocked_by: []
---

## Question

Settle the terms still loose: Holding vs Position vs lot (a 401(k) contribution source); Account (a Plaid account, an Accounts-sheet row, or a login/item); Institution; Source (the Assets column and its values); Class and Class Pct; look-through. Which go in `GLOSSARY.md`, with what definitions, and what does each one replace?

## Resolution

Decided with the owner, 2026-11-07. Added to `GLOSSARY.md`:
- Holding and Lot; "position" is to be avoided.
- Account, Linked account and Login; Plaid's "item" is to be avoided.
- Institution.
- Class, Class Pct, Category and Parent: the roll-up levels from the Targets
  sheet.
- Look-through and Source. The specific Source values stay in the README.

Side finding: on the Assets sheet, VMCPX uses Class `U.S. Mid Mkt`, which has
no Targets row, so the report rolls it up under "Other". This is a data fix
for the owner, not part of this map.
