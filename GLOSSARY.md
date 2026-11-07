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

**Holding**
One fund or bond in one Account. It is one row on the Holdings sheet.
_Avoid_: position

**Lot**
A piece of a Holding that the institution reports separately, e.g. one per
401(k) contribution source. Lots of the same fund combine into one Holding.
_Avoid_: position, tax lot (unless cost basis is meant)

**Account**
An account as the owner names it on the Accounts sheet (e.g. `Spouse 401k`).
Everything is reported by Account.

**Linked account**
An account at an institution that Plaid reads, mapped to exactly one Account.

**Login**
One set of credentials at one institution. It can cover several linked
accounts.
_Avoid_: item (Plaid's word)

**Institution**
The firm that holds an Account (Fidelity, Vanguard, Empower). One institution
can have several Logins, which Plaid may name differently.

**Class**
An asset class with an allocation target (e.g. U.S. Total Mkt, TIPS).
_Avoid_: asset type, security type

**Class Pct**
The share of a fund that falls in one Class.

**Category**
A group of Classes that the report totals together (e.g. TIPS and U.S. Bonds
→ U.S. Bonds).

**Parent**
A group of Categories (Stocks, Bonds, Short term).

**Look-through**
Splitting a fund into Classes using the holdings listed in its own regulatory
filing. For a fund that holds other funds, it follows through to the
underlying funds.

**Source**
Where an Assets row's split came from: a filing, a comparable fund, or the
owner by hand.
