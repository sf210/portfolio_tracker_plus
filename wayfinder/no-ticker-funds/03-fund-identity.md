---
id: 03
title: How is a no-ticker fund identified in Holdings and Assets?
label: wayfinder:grilling
status: closed
assignee: claude
blocked_by: [01, 02]
---

## Question

What value goes in the Ticker column of Holdings, and is used as the Assets key, for a fund with no market ticker? The candidates are Plaid's plan code (`XPLNLS`), the fund name, Plaid's `security_id`, or a user-chosen alias mapped from one of these. Test each against two plans offering "Target Date 2030 Fund" with different underlying holdings, a fund rename, and a plan-code change.

## Resolution

Decided with the owner, 2026-11-07.

1. **Term.** The term is **unlisted fund**: no exchange listing, no market
   quote, priced only by the institution. It is defined in `GLOSSARY.md`. A
   plan code such as `XPLNLS` is not a ticker.
2. **Detection.** A linked holding is unlisted when Plaid's `close_price` is
   null **or** `proxy_security_id` is set. The null-ticker and ticker-shape
   checks are dropped because they are redundant. On the 2026-11-07 snapshot
   this rule flags exactly the six plan funds and none of the 37 listed
   securities.
3. **Key.** For an unlisted fund, the Holdings `Ticker` and the Assets key are
   **Plaid's fund `name`, trimmed**. Plaid's `ticker_symbol` is ignored even
   when present. Rejected options:
   - the plan code, which is meaningless on a report and gets sent to Yahoo;
   - `institution_security_id`, which is missing for `XPLNLS` and `XPLNLV`;
   - `security_id`, which is unreadable and may change;
   - a user alias table, which is extra upkeep for a rare problem.
4. **Same name for different funds.** `fetch` warns when one name maps to more
   than one Plaid `security_id` in a single fetch, whether within an account
   or across logins. It warns only; the key is not qualified automatically.
   No collision exists today.
5. **Renames.** A renamed fund shows up under its new name. `fetch-composition`
   adds an Assets row with a blank Class, and the report warns that the fund
   is Unclassified until the owner renames the old Assets rows. The README
   should document this. No other handling.
6. **Hand-entered accounts.** Use the fund's name exactly as the statement
   prints it. Leave Broker Price blank only if a Price Override is set.
7. **Assets `Name`** for an unlisted fund is the same as its key, which is
   current `fetch-composition` behaviour.

Consequence for pricing: a name containing a space already fails
`fetch_prices.py`'s ticker pattern, so it never reaches Yahoo. A one-word
fund name would still reach Yahoo, which the pricing ticket must cover.
