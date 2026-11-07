# Wayfinder maps (local-markdown tracker)

Each effort is a folder: `map.md` (labelled `wayfinder:map`) plus one file per
ticket, `NN-slug.md`. The ticket's id is its `NN`.

Ticket frontmatter:

```yaml
id: 01
title: <name, used when referring to the ticket>
label: wayfinder:research | wayfinder:prototype | wayfinder:grilling | wayfinder:task
status: open | closed
assignee:            # empty = unclaimed; set it to claim before any work
blocked_by: [02, 03] # native blocking; unblocked when all are closed
```

The resolution is appended as a `## Resolution` section when the ticket is closed.

Frontier (open, unclaimed, every blocker closed):

```bash
grep -l '^status: open' wayfinder/<map>/[0-9]*.md | xargs grep -l '^assignee: *$'
# then drop any whose blocked_by lists a ticket still open
```
