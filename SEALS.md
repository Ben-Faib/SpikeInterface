# SEALS.md - what each run decided, moved, and needs from Ben

*Ben's read-in-30-seconds file, and the source `/status` reads. Every sealing session
appends ONE block to the ledger (five lines, one sentence each - the cap is the point),
rewrites any pinned line its work changed, and edits OPEN if it created or closed a need.
Long prose belongs in commit messages, LESSONS and the briefs, never here. A need left only
in a chat summary is a need Ben never sees. Ledger before Spike 2.0: tag
`pre-cleanup-2026-10-06`.*

---

## Where we stand (pinned - one line per job; a seal that changes one rewrites it)

- **The app**: Spike 2.0 is the baseline (`goals/GOAL_V2.md`): a rail of six stages with one
  next step, every setting editable in place, any run re-run from its recipe, and per-unit
  pages with real plots on 4 Judge (`1f72fdb`).
- **The pipeline**: load → sort (4 local sorters, Docker fallback) → analyzer + six metrics on
  every surface; the noise-floor canary holds at ~4 µV.
- **Curation**: one record per run (merge / split / label from 4 Judge or Phy), applied to a
  curated Sorting with re-scored metrics; every surface says curated or raw.
- **Runs**: versioned, never clobbered, regenerable with an honest match report.
- **Probe**: `nnx-a1x16-3mm-100` by default; identity wiring is the standing assumption.
- **The science picture**: 4 strong cells recovered at 96-100% against Ben's manual sort; no
  swept sorter splits the merged pairs (facts of record: `docs/INVARIANTS.md`).
- **The lab box**: the Windows acceptance run has not reported yet; GPU sorters not started.
- **The repo**: work is on `Version-2` (`main` last moved 2026-08-19); the board was reset to
  the Spike 2.0 baseline on 2026-10-06, and every run and review uses Opus 5.5.

## OPEN - needs Ben

- **The next queue**: `ROADMAP.md` holds one empty slot for tonight's run; it waits on Ben's
  direction. *(opened 2026-10-06)*

---

## The ledger (newest first)

**2026-10-06 - board reset: progressive disclosure, Opus 5.5, Spike 2.0 as the baseline**
- Did: turned CLAUDE.md into an index, moved structure and rules to `docs/ARCHITECTURE.md` and `docs/INVARIANTS.md`, put the sealing contract in LOOPS.md, moved every agent to Opus 5.5, and reset ROADMAP, SEALS, LESSONS and NORTHSTAR to what is true from Spike 2.0 on.
- Means: every session loads about a tenth of what it used to and opens detail only when its task needs it, and the board says only what holds now.
- Moved: `babb705` through this seal; always-loaded CLAUDE.md ~5.1k → ~0.5k tokens, ROADMAP ~8.5k → ~0.4k, SEALS ~11.2k → ~1.0k; suite 682 passed / 1 skipped, 16 snapshots; old text at tag `pre-cleanup-2026-10-06`.
- Needs Ben: direction for the next queue, starting with tonight's run (OPEN).
- Next: write tonight's brief and paste prompt into ROADMAP from Ben's direction.

**2026-09-27 - Spike 2.0: built, tested end to end, reviewed**
- Did: built the v2.0 mockups as the app (rail of six stages, one next step, a pane per stage, Settings for every value, palette, Runs + reproduce, unit evidence on 4 Judge), a sandboxed harness that drives every function on the real data, and folded a fix-first review (15 findings, incl. stale evidence after a re-sort, NaN input crashes, a Docker toggle that switched itself off).
- Means: a researcher can see where the recording stands and what to do next, change any setting in place, judge units by their waveforms, and re-run any sort from its recipe to check its values - and one command proves all of it works.
- Moved: `2c43891` + `a45749d` + `24bb8b7`; suite 675 green, 16 snapshots, harness 16 PASS / 0 FAIL / 1 MANUAL (canary ~4 µV, reproduce REGENERATED); UX2 0/A-D absorbed.
- Needs Ben: the Windows acceptance run (OPEN: V2), and a first look at the app on this Mac.
- Next: UX2-E (the HTML pages as one site) or the lab-box GPU track (WD), after the Windows run reports back.
