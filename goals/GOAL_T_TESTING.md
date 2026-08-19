# GOAL T - Testing procedures: pin journeys and contracts before the surfaces churn

## Intent

Ben's 2026-08-18 mandate: build out better testing procedures so things are tested properly.
The overhaul (GOAL_D) will rewrite most visible surfaces, and the existing Pilot suite pins
layout details that are about to churn - worse, a green suite has actively defended a bug
before (LESSONS S1). The T track makes the tests assert what must stay true (journeys,
contracts, honesty states) and makes visual change *reviewable* instead of either untested
or fought by brittle assertions.

## Task

- **T1 - the harness** (delegated to the peer session, 2026-08-18): Textual snapshot
  testing (pytest-textual-snapshot or equivalent) with baselines of today's dashboard at
  representative sizes + the sort-progress and confirm modals; a structural golden check
  for `outputs/report.html` (sections present and ordered, required tables/figures
  non-empty - not pixels), skipped cleanly without a saved sort; contract tests for the
  `sort_progress` JSON protocol (event shapes, phase ordering, stdout purity); a
  `tests/README.md` documenting deliberate re-baselining.
- **T2 - journey-first refactor** (after D1/D2 land): retire layout-detail assertions the
  redesign obsoletes in favor of journey assertions (explore→sort→report happy path, the
  0-unit amber path, the failure-card path, cancel mid-sort), keeping the never-clip tests.
- **T3 - honesty-state coverage**: every empty/zero/error state named in DESIGN_UX §1.7
  gets a test that drives it and asserts the next-step hint is shown.

## Definition of done

T1: suite green including the new tests; re-baselining documented. T2/T3: suite green; the
retired assertions enumerated in the seal commit message (deliberate deletion, not decay);
journey coverage includes every path named above. Fable review per slice.

## Boundaries and known traps

- The suite remains necessary-not-sufficient for sort-adjacent work - nothing in this track
  replaces the 30 s sort smoke + canary (LESSONS S1 stands).
- Snapshot tests must be deterministic (fixed terminal size, frozen animations/time where
  Textual allows); a flaky snapshot is worse than none.
- Golden report checks assert structure, never pixel or byte equality (Plotly output isn't
  stable enough, and that's fine).
- Tests keep injecting the fake controller through the Protocol - no SpikeInterface import
  sneaks into view tests.
