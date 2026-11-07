---
id: 01
title: Which Plaid fields mark a security as having no market ticker?
label: wayfinder:research
status: closed
assignee: claude
blocked_by: []
---

## Question

Which fields of Plaid's investments security object (`ticker_symbol`, `cusip`, `isin`, `sedol`, `type`, `subtype`, `market_identifier_code`, `institution_security_id`, `institution_id`, `proprietary_security_type`, `close_price`, `update_datetime`, …) can reliably tell an exchange-traded security from a plan fund or collective trust that has only an institution-assigned code? Is `security_id` stable over time for the same fund? What does Plaid document about `institution_price` and `institution_price_as_of`?

## Resolution

Findings are on branch `research/plaid-no-ticker-fields`, in
`wayfinder/no-ticker-funds/research/01-plaid-no-ticker-fields.md`. Sources are
plaid.com/docs, Investments API reference.

- Plaid has no proprietary, plan-fund or collective-trust flag. `type` and
  `subtype` give such funds the same values as retail funds (`mutual fund`,
  `other`).
- `ticker_symbol` may be an institution's short identifier for a non-public
  security, so a ticker being present proves nothing. `cusip` and `isin` are
  null without a CUSIP license, and `sedol` is deprecated.
- The strongest signal is `close_price`, which is documented as null for
  non-public securities. It can also be null for a listed security with no
  recent close. A set `proxy_security_id` is another sign the security is
  private.
- `security_id` "does not typically change, but may change", so it is not a
  permanent key.
- `institution_price` is the institution's last price, and
  `institution_price_as_of` may be null.
- Recommended rule: a security is not a market ticker if `ticker_symbol` is
  null, `close_price` is null, `proxy_security_id` is set, or the ticker fails
  the shape check `^[A-Z]{1,5}([.-][A-Z]{1,2})?$`. As a safety net, use
  `institution_price` when Yahoo has no quote or is more than about 20% away
  from it.
- Correction to the research note: the note says the shape check misses
  `XPLNLS`. It doesn't, because six letters fails `{1,5}`. `XPLNLS` is caught
  by both the shape check and `close_price`.
