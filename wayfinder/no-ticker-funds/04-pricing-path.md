---
id: 04
title: How are no-ticker funds kept out of the Yahoo lookup and priced from Broker Price?
label: wayfinder:grilling
status: open
assignee:
blocked_by: [01, 03]
---

## Question

How does the price step know not to ask Yahoo about a fund with no market ticker? The options are a rule based on Plaid fields, a marker on the Holdings or Assets row, or a Price Override. And when should the report trust Broker Price, warn about it, or treat it as stale?

Context from the fund-identity decision: unlisted funds are keyed by fund name. A name containing a space already fails the ticker pattern in `fetch_prices.py` and skips Yahoo, but a one-word name would not.
