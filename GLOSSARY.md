# Glossary

**Unlisted fund**
A fund with no exchange listing, and so no market quote. Its only price is
the one the institution reports. Typical examples are 401(k) plan funds and
collective investment trusts. Some institutions attach an internal plan code
to an unlisted fund (e.g. `XPLNLS`). That code is not a ticker.
_Avoid_: no-ticker fund, trust (when meaning the general case), plan code
(when meaning the fund)

**Broker Price**
The per-share price the institution reports for a holding, as of its Price
Date. It is the only price an unlisted fund has.
_Avoid_: institution price, NAV (when meaning this field)

**Quote**
A market price for a listed security from a public price feed.
_Avoid_: price (when the source matters)

**Price Date**
The date the institution says its Broker Price applies to. This is not the
date the holding was fetched.

**Price Override**
A fixed price the owner sets for a ticker. It wins over every other price.

**Comparable fund**
A listed fund the owner chooses to stand in for an unlisted fund's asset-class
split, written `like TICKER` in the Assets Source column. It is always the
owner's choice, never taken from the institution or Plaid.
_Avoid_: proxy (Plaid's "proxy security" is a different thing and is not
trusted)
