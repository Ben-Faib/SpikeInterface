# LOOPS.md - how the workbench gets built

The build method: loops with machine-checkable stop conditions, verification encoded as a
skill, and the repo's real gates as the stop-condition engine. This file is the playbook, the
prompt template, and the sealing contract. Briefs live in `goals/`; the live queue lives in
`ROADMAP.md`.

## The gates (this repo's measuring sticks - they already exist)

Every loop stops on one or more of:

1. **The test suite** - `uv run python -m pytest tests/` (Textual Pilot + unit tests).
   Necessary, never sufficient for sort-adjacent work (LESSONS S1: a green suite once
   enforced a bug that broke all sorting).
2. **The sort smoke** - `uv run python scripts/run_sorting.py --duration 30 --probe <active>`.
   The real feedback loop for anything sort-adjacent. Its canary: **noise floor ~4 µV**. A
   ~1 µV reading means the gain got re-applied - a correctness failure regardless of what
   else passed.
3. **The loader smoke** - `uv run python scripts/verify_install.py` after touching
   `blackrock_io.py`.
4. **A containerized sort** - one Docker-backed run when Docker paths were touched.
5. **A real render** - report/comparison changes are checked by building the HTML and
   looking at it; app changes by the Pilot journeys (and a real launch for anything Pilot
   can't see).
6. **The workbench harness** - `uv run python scripts/check_workbench.py` for anything that
   spans functions; it is also the Windows acceptance test.

The `verify-spike` skill maps change-type → gates and is the done-check inside every loop.

## Fit assessment (which loop type for which work)

- **Goal-based runs - the primary tool.** One brief (or slice of one) per fresh session,
  driven by a paste prompt from `ROADMAP.md` that names the brief, the checkable
  done-condition, and the boundaries. Plain Opus 5.5 prompts, no wrapper.
- **Turn-based + skills - the workhorse.** Single prompts self-verify via `verify-spike`
  instead of handing back unchecked edits.
- **Workflows (multi-agent) - for wide passes.** Audits across the codebase, adversarial
  verification of findings, review panels over a finished slice. Opt-in per brief; pilot on
  a small slice first.
- **Time-based (`/loop`) - for babysitting long runs.** A full-recording Docker sort or a
  multi-sorter sweep; match the interval to the run.
- **Cloud schedules - code-only.** The recording is local-only and gitignored, so remote
  sessions can lint, refactor, and test pure-code paths but can never run a sort.

## The doctrine

1. **A change is done when its gate says so**, not when it looks done. Every loop names its
   gates up front, from the list above; a brief may add checks but never subtracts the
   standing ones.
2. **Every goal run cites its brief.** The brief carries intent, boundaries, and definition
   of done; the prompt carries the checkable condition. No freestanding goals.
3. **Fresh-context review - one pass.** Substantive slices get a single fresh-context review
   of the full diff against the brief and `docs/INVARIANTS.md` before being called done (the
   `reviewer` agent). This is independent judgment on a finished diff - a session must NOT
   stack extra self-verification passes, re-run gates it already ran green, or spawn
   workhorse agents to re-check itself. Run the real gates once, then hand the diff to the
   reviewer. Trivial mechanical work seals without a review.
4. **Lessons compound.** `LESSONS.md`, one lesson per entry. When a loop iteration fails,
   fix the instance *and* encode the fix into a test, skill, brief or rule so every future
   iteration inherits it.
5. **One model: Opus 5.5** (Ben, 2026-10-06). Every run and every review runs on Opus 5.5:
   `scout`, `builder`, `reviewer` and `finalizer` all use `model: opus`. Workflow `agent()`
   calls pass `model: "opus"` explicitly, since they would otherwise inherit the session model.
6. **Pilot before fan-out.** `--duration 30` before any full sort; a small slice before any
   wide workflow; variant outputs go to new runs in the run store, never overwritten.

## Sealing (the between-run contract)

Every goal run ends sealed. Git plus the board files are the state: a fresh session re-enters
by reading them, never by asking Ben what happened.

1. Run the gates once and, for substantive work, fold the review (doctrine 3).
2. Update `ROADMAP.md`: the NOW box, the item's queue row, and any constant a later prompt
   quotes. A stale marker is a defect.
3. Write any surprise worth keeping to `LESSONS.md`: one entry, with where the fix is encoded.
4. Append one five-line block to `SEALS.md`'s ledger - did, means, moved, needs Ben, next;
   one sentence each - and rewrite any pinned "Where we stand" line or OPEN item the work
   changed.
5. Commit with a descriptive message, staging explicit paths, in the same breath as the
   board edits (LESSONS S7); re-check `git status` first, since others edit concurrently.
6. The closing chat summary says the same five things as the SEALS block and stops, under
   200 words.

A run that stops short still seals: commit partial state and say plainly what is done, what
is not, and why.

## The prompt template (the live filled-in queue lives in ROADMAP.md)

Start sessions from this repo's root so CLAUDE.md, the agents, and the skills load. Prompts
are plain, self-contained Opus 5.5 prompts: open with intent, then the task, verifiable
done-criteria, hard boundaries, and close with "Seal per LOOPS.md". Never bolt on generic
"verify your work" lines - the gates and the review pass already cover that.

```
<Intent: who this serves and what it unlocks.> Execute goals/GOAL_<X>.md (slice N if
sliced). Done when: <the brief's checkable conditions, with the gates named>. Boundaries:
<the brief's>. Seal per LOOPS.md.
```

**Babysit (only when a multi-hour run actually exists):**
```
/loop 15m check the running sort/sweep: append progress to the run's notes, flag a stalled
phase. Restart at most twice; on a third stall stop the loop and report what's wrong. Stop
when it completes.
```

## What this file is not

Not a place for product decisions (`NORTHSTAR.md`), per-brief detail (`goals/`), or the
queue (`ROADMAP.md`). When a loop stalls or overreaches, the fix lands here or in a skill -
that is how the system improves.
