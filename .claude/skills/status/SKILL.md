---
name: status
description: Produce Ben's workbench status report - what happened, what needs him, what runs next. Invoke when Ben says "status", "where are we", "sitrep", or asks for the state of the build in this repo.
---

# The status report (this repo)

**Read exactly three things - nothing else.** Reading more is how status reports bloat:

1. `SEALS.md` - the pinned "Where we stand" lines, the OPEN needs, and the last few ledger
   blocks.
2. `ROADMAP.md`'s NOW box - what runs next and what's gated.
3. `git log --oneline -5` - confirms what actually sealed, and catches a session that landed
   work without appending to SEALS.md. If git shows a landing SEALS.md lacks, say so in one
   line - that defect in the between-run contract is worth more to Ben than any detail.

Write it BLUF, one screen: open with the single sentence that changes what Ben does next (if
something is waiting on him, that is the sentence). Then three short sections - what sealed
recently, what needs Ben (verbatim from OPEN), what runs next (the NOW box's move). Plain
sentences a smart person who watched none of the runs can read: no bare metric names, no
project shorthand standing alone, every number translated into what it means.

Only if Ben asks for the long version ("full", "detailed"): add the queue table from
ROADMAP.md and the pinned "Where we stand" lines in full. Never longer than that.
