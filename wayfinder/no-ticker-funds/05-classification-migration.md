---
id: 05
title: How are no-ticker funds classified, and how do today's manual rows migrate?
label: wayfinder:grilling
status: closed
assignee: claude
blocked_by: [03]
---

## Question

How does a no-ticker fund get its asset-class split? The options are `like TICKER`, a manual split, or something new. What happens on the first fetch to the hand-entered 401k A Holdings rows and their name-keyed Assets rows, so the classification survives the switch to Plaid data?

## Resolution

Decided with the owner, 2026-11-07.

1. **Mechanism.** An unlisted fund gets its split from a **comparable fund**
   (`like TICKER` in Source), using that fund's N-PORT look-through. The
   owner's manual split is the fallback.
   - A successful look-through replaces the Class rows.
   - A failed one leaves them as they are. That's the manual split before the
     first success, and the last successful look-through after it.
   - The owner's original split is not kept separately; this was accepted.
   - Plaid's `proxy_security_id` is never used.
   - This is current `fetch-composition` behaviour for `like` rows, so no new
     mechanism is needed.
2. **Meaning of `manual`.** Source `manual` means "never look this up". It
   is used only where no comparable fund applies.
3. **Starting values:**

   | Assets key | Source |
   |---|---|
   | The Vanguard Target Retire 2070 Trust I | `like VLXVX` |
   | The Vanguard Target Retire 2025 Trust I | `like VTTVX` |
   | Target Date 2030 Fund | `like VTHRX`. The owner sourced today's manual split from the plan fact sheet but expects it to drift, so the comparable fund tracks it better. |
   | U.S. Large Cap Stock Index Fund | `like VOO` |
   | U.S. Core Bond Index | `like BND` |
   | Capital Preservation Fund | Cash 100%, `manual` |

4. **One-time migration, done by hand before the first fetch of Empower
   401k A.** The spec and README will document it.
   1. On Assets, rename `US Large Cap Index Fund` to
      `U.S. Large Cap Stock Index Fund`.
   2. Set each Source as in the table. The existing Class rows stay as the
      fallback.
   3. Add the Capital Preservation Fund row.
   4. Run `linked-accounts fetch`, then `fetch-composition`.

   `fetch` replaces 401k A's hand-entered Holdings rows, so they need no step. A
   missed rename shows up as an Unclassified warning. The only workbook format
   change is the two new Holdings columns from the pricing ticket.

New glossary term: Comparable fund.
