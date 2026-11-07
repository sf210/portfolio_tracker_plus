---
label: wayfinder:map
title: Holdings without a market ticker
---

## Destination

A spec, ready to implement, for linked-account holdings that have no market
ticker (401(k) plan funds and trusts at Empower, Vanguard plan funds). It
covers how each fund is identified, priced, classified and shown in the
report. Alongside it: project documentation for the owner and future Claude
sessions (a glossary, an architecture and data-flow overview, and a repo
`CLAUDE.md`). The README stays the user guide.

## Notes

- Domain: personal portfolio tracker. Plaid Investments -> Holdings sheet of
  `src/portfolio_input.xlsx` -> price fetch (Yahoo, FedInvest) -> N-PORT
  look-through on the Assets sheet -> HTML report.
- Grilling and domain-modeling tickets: call both skills. Record terms in
  `GLOSSARY.md` as they are resolved.
- Use Plaid's real shares and the institution's price (Broker Price), not
  $1 per share. Decided while charting, 2026-11-07.
- Scope covers every linked fund without a market ticker (401k B,
  401k A, 401k C). Accounts entered by hand only need to follow the
  naming rule the spec sets.
- Facts found while charting (2026-11-07, read-only `/investments/holdings/get`):
  - 401k A returns 13 lots across 3 funds. Their
    `ticker_symbol` values are plan codes (`XPLNLS`, `XPLNLV`,
    `TARGET.DATE.2030.FUND`), `cusip` is null, `type` is `mutual fund`,
    `close_price` is null, and `institution_price` is about $10.5. The lot
    values add up exactly to the account balance.
  - The Holdings and Assets rows for 401k A's funds were entered by hand, keyed on
    names ("Target Date 2030 Fund", "US Large Cap Index Fund") at $1/share.
  - 401k B's trusts come through with no ticker, so the code uses the fund
    name. 401k C has "U.S. Core Bond Index".
  - `fetch_prices.py` sends any ticker matching `[\w.^=-]+` to Yahoo, and plan
    codes match that pattern.
- Tracker: local markdown, see `wayfinder/README.md`.

## Decisions so far

- [Which Plaid fields mark a security as having no market ticker?](01-plaid-no-ticker-fields.md): Plaid has no explicit flag. Detect by a null ticker, null `close_price`, a set `proxy_security_id`, or a non-symbol ticker shape, with an `institution_price` fallback. `security_id` is not a permanent key.
- [Snapshot raw Plaid holdings for every linked login](02-plaid-holdings-snapshot.md): 6 no-ticker funds (3 in 401k A, 2 in 401k B, 1 in 401k C). A null `close_price` or a set `proxy_security_id` flags exactly these and nothing listed. Plaid's proxies are wrong matches; never use them. No security has a CUSIP.
- [How is a no-ticker fund identified in Holdings and Assets?](03-fund-identity.md): the term is **unlisted fund**, meaning Plaid's `close_price` is null or a `proxy_security_id` is set. The key is Plaid's fund name; the plan code is ignored. Fetch warns on a name collision. A rename shows up as an Unclassified warning.
- [How are no-ticker funds kept out of the Yahoo lookup and priced from Broker Price?](04-pricing-path.md): `fetch` writes new Holdings columns, Price Source (`broker`) and Price Date. A `broker` row uses Broker Price and skips Yahoo. The report warns when a price is more than 5 days old and shows `price · broker MM-DD`.

## Not yet specified

- What the architecture and data-flow doc covers, and how deep it goes.
- Which glossary terms need a sharp definition: Holding vs Position vs lot;
  Source; Account (Plaid account vs Accounts-sheet row).

## Out of scope

- Checking Yahoo quotes against Broker Price for listed holdings. Unlisted funds never reach Yahoo, so it isn't needed here (decided in [How are no-ticker funds kept out of the Yahoo lookup and priced from Broker Price?](04-pricing-path.md)).
- The bond cross-check in `update_workbook` never fires because Plaid gives Fidelity's TIPS no CUSIP (found in [Snapshot raw Plaid holdings for every linked login](02-plaid-holdings-snapshot.md)). It's a separate bond fix, not part of no-ticker funds.
- Combining with `~/finance/planning/annuity`: a separate future effort.
- Accounts entered by hand (Optum HSA, Optum Invest, mydeferralselect), apart
  from following the naming rule.
