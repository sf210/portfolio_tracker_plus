---
id: 06
title: Where do the project docs live?
label: wayfinder:grilling
status: closed
assignee: claude
blocked_by: []
---

## Question

Where do `GLOSSARY.md`, the architecture doc, ADRs and the repo `CLAUDE.md` go, given that `docs/` is git-ignored to keep the Plaid master agreement out of git? Options: narrow the ignore rule to the agreement file and use `docs/`, or put the docs in another folder.

## Resolution

Decided with the owner, 2026-11-07.

1. Narrow the `.gitignore` rule from `docs/` to `docs/plaid_master_agreement`.
   The agreement stays where it is and stays out of git; the rest of `docs/`
   is committed.
2. Layout:

   | Doc | Location |
   |---|---|
   | User guide | `README.md` at the root, unchanged |
   | Glossary | `GLOSSARY.md` at the root, already there |
   | Orientation for Claude sessions | `CLAUDE.md` at the root, short, points at the others |
   | Architecture and data flow | `docs/ARCHITECTURE.md` |
   | Decision records | `docs/adr/`, created only when one is needed |
   | Wayfinder maps | `wayfinder/` at the root, already there |
