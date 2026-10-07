# ROADMAP.md - the live build queue

*The one place to look for what runs next: the NOW box, then the queue, then the paste
prompts. Prompts are plain Opus 5.5 prompts built from `LOOPS.md`'s template, each run in a
fresh session from the repo root and closing with "Seal per LOOPS.md". Keep it true: a
sealing session updates the NOW box and its queue row, and a finished item leaves the queue
(its record is the SEALS block and git). Queues before Spike 2.0: tag `pre-cleanup-2026-10-06`.*

## ▶ NOW - updated 2026-10-06: **Spike 2.0 is the baseline; the next queue is Ben's to set**

- Baseline: Spike 2.0 (`goals/GOAL_V2.md`), `2c43891` build · `a45749d` the sandboxed
  end-to-end harness · `24bb8b7` review folded; harness 16 PASS / 0 FAIL / 1 MANUAL on the
  real data, canary ~4 µV. Since then: unit pages on 4 Judge (`1f72fdb`).
- Board reset (2026-10-06): CLAUDE.md is an index; structure and rules live in
  `docs/ARCHITECTURE.md` and `docs/INVARIANTS.md`; every run and review uses Opus 5.5.
- **Next: Ben's direction**, starting with tonight's run. Nothing below runs until he sets it.

## Queue

| # | Item | Brief | Done when (gates) | State |
|---|---|---|---|---|
| 1 | Tonight's run | to write from Ben's direction | from the brief | waiting on Ben |

## Paste prompts

None yet. Each queued item gets one here, from `LOOPS.md`'s template, when it is ready to run.

## Rules for this file

1. **Keep it true.** A stale NOW box, status marker, or constant inside a prompt is a defect;
   fix it on sight.
2. **Finished work leaves.** A sealed item's row and prompt go; SEALS and git keep the record.
3. **Conditional behavior goes in the prompt, not in a global rule** - what matters for one
   item is written into that item's prompt, unconditionally.
