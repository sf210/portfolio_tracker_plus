---
id: 02
title: Snapshot raw Plaid holdings for every linked login
label: wayfinder:task
status: closed
assignee: claude
blocked_by: []
---

## Question

Save the raw `/investments/holdings/get` response for each linked login to a git-ignored file under `data/` (tokens left out). List every security that has no CUSIP or whose ticker isn't a market symbol, with all of its fields, so the identification and pricing rules can be checked against real data.

## Resolution

Done 2026-11-07. Raw `/investments/holdings/get` responses for all four logins
are in `data/plaid_snapshots/<Institution>_20261107.json`. That folder is
git-ignored; the `item` and `request_id` fields were removed, and the files
contain no access tokens. 43 securities, all with distinct `security_id`s.

**No-ticker funds held in mapped accounts (6):**

| Account | Plaid name | `ticker_symbol` | `institution_security_id` | Price | Value |
|---|---|---|---|---|---|
| 401k A | Target Date 2030 Fund | `TARGET.DATE.2030.FUND` | `XPL2030` | 10.543877 | … |
| 401k A | U.S. Large Cap Stock Index Fund | `XPLNLS` | null | 10.877849 | … |
| 401k A | Capital Preservation Fund | `XPLNLV` | null | 10.343791 | … |
| 401k B | The Vanguard Target Retire 2070 Trust I | null | `XTRS70` | 32.05 | … |
| 401k B | The Vanguard Target Retire 2025 Trust I | null | `XTRS25` | 96.18 | … |
| 401k C | U.S. Core Bond Index | null | `X365` | 11.212596 | … |

All six funds have:
- `type` = `mutual fund` with `subtype` null;
- `cusip` null;
- `close_price` null;
- `market_identifier_code` null;
- `proxy_security_id` set;
- `institution_price_as_of` set (the 11-06 or 11-07 date).

**Checking the detection rule from the Plaid-fields research:** `close_price`
null or `proxy_security_id` set flags exactly these six and nothing else. No
listed security is flagged; every ETF, mutual fund and money market fund has
a `close_price`. Not one security in the snapshot has a CUSIP, because the
account has no CUSIP license. So a missing CUSIP tells us nothing.

**Proxy securities are wrong matches.** They look like matches on the fund
name and must not be used for pricing or classification:
- Capital Preservation Fund → CBNK (Capital Bancorp, an equity)
- U.S. Large Cap Stock Index Fund → UGSDX (an ultra-short government bond
  fund)
- Target Date 2030 Fund → PDIZX (a Franklin 2030 fund; plausible, but not the
  plan's fund)
- Vanguard 2070 Trust → FIRE (Supreme Cannabis)
- Vanguard 2025 Trust → Hartford Target Retirement 2050 R5
- U.S. Core Bond Index → GROW (U.S. Global Investors stock)

**Facts for the identity decision:**
- 401k A's two large funds have different `security_id`s that share a
  15-character prefix (`rJ6M41My0wF…`).
- `institution_security_id` is present for four of the six funds and missing
  for `XPLNLS` and `XPLNLV`.
- `institution_id` is inconsistent (`ins_11`, `ins_116552`, `ins_115616`, or
  null).

**Side finding (bonds, outside this map):** Fidelity's TIPS also have null
CUSIPs. So the "linked bond not on the TIPS sheet" warning in
`update_workbook` (`if p["cusip"] and …`) never fires.
