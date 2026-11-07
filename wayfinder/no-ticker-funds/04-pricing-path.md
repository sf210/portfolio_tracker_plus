---
id: 04
title: How are no-ticker funds kept out of the Yahoo lookup and priced from Broker Price?
label: wayfinder:grilling
status: closed
assignee: claude
blocked_by: [01, 03]
---

## Question

How does the price step know not to ask Yahoo about a fund with no market ticker? The options are a rule based on Plaid fields, a marker on the Holdings or Assets row, or a Price Override. And when should the report trust Broker Price, warn about it, or treat it as stale?

Context from the fund-identity decision: unlisted funds are keyed by fund name. A name containing a space already fails the ticker pattern in `fetch_prices.py` and skips Yahoo, but a one-word name would not.

## Resolution

Decided with the owner, 2026-11-07.

1. **Marker.** `fetch` writes a new Holdings column, **Price Source**: `broker`
   for an unlisted fund and blank otherwise. The owner may type `broker` on a
   hand-entered row.
   - For a `broker` row, the report uses Broker Price and never a Quote. The
     order is Price Override → Broker Price.
   - `fetch-prices` doesn't send a key to Yahoo when every Holdings row for
     that key is `broker`.
   - The ticker-shape check stays only as a fallback for unmarked rows.
   - Rejected options: relying on the shape check alone, because a one-word
     name would still reach Yahoo; and always preferring Broker Price, which
     would replace the Quote for listed holdings too.
2. **Price Date.** `fetch` stores Plaid's `institution_price_as_of` in a new
   Holdings column, **Price Date**. The report warns when a `broker` holding's
   Price Date is more than 5 calendar days before the report date, or when it
   is missing.
3. **Missing Broker Price.** If Plaid's `institution_price` is null, `fetch`
   uses `institution_value / quantity`. If both are missing, it warns and the
   report skips the holding, as it does today.
4. **Report.** In the holdings table, a broker-priced row shows its price as
   `10.54 · broker 11-06`. Listed rows are unchanged.
5. **Cross-check against Yahoo.** Ruled out of scope. It would only protect
   listed holdings.

New glossary terms: Broker Price, Quote, Price Date, Price Override.
