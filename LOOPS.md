# LOOPS.md — how the workbench gets built

The build method: loops with machine-checkable stop conditions, verification encoded as a
skill, and the repo's real gates as the stop-condition engine. This file is the playbook and
the prompt-template library. Phase briefs live in `goals/`; the live queue with filled-in
prompts lives in `ROADMAP.md`.

## The gates (this repo's measuring sticks — they already exist)

Unlike a greenfield project, the number-makers are built. Every loop stops on one or more of:

1. **The test suite** — `uv run python -m pytest tests/` (Textual Pilot + unit tests).
   Necessary, never sufficient for sort-adjacent work (LESSONS S1: a green suite once
   enforced a bug that broke all sorting).
2. **The sort smoke** — `uv run python scripts/run_sorting.py --duration 30 --probe <active>`.
   The real feedback loop for anything sort-adjacent. Its canary: **noise floor ~4 µV**
   (3.88–4.02 across all saved sorts). A ~1 µV reading means the gain got re-applied — a
   correctness failure regardless of what else passed.
3. **The loader smoke** — `uv run python scripts/verify_install.py` after touching
   `blackrock_io.py`.
4. **A containerized sort** — one Docker-backed run when Docker paths were touched.
5. **A real render** — report/comparison changes are checked by building the HTML and
   looking at it; menu changes by the Pilot journeys (and a real launch for anything Pilot
   can't see).

The `verify-spike` skill maps change-type → gates and is the done-check inside every loop.

## Fit assessment (which loop type for which work)

- **Goal-based runs — the primary tool.** One phase brief (or slice of one) per fresh
  session, driven by a paste prompt from `ROADMAP.md` that names the brief, the checkable
  done-condition, and the boundaries. Plain Fable prompts, no wrapper.
- **Turn-based + skills — the workhorse.** Single prompts self-verify via `verify-spike`
  instead of handing back unchecked edits.
- **Workflows (multi-agent) — for wide passes.** Audits across the codebase, adversarial
  verification of findings, review panels over a finished slice. Opt-in per brief; pilot on
  a small slice first. Width per the driving model (global working agreement).
- **Time-based (`/loop`) — for babysitting long runs.** A full-recording Docker sort or a
  multi-sorter sweep; match the interval to the run. Little use until such sweeps exist.
- **Cloud schedules — code-only.** The recording is local-only and gitignored, so remote
  sessions can lint, refactor, and test pure-code paths but can never run a sort. Anything
  needing the data runs on this machine (or, for WD, the lab box).

## The doctrine

1. **A change is done when its gate says so**, not when it looks done. Every loop names its
   gates up front, from the list above; a brief may add phase-specific checks (e.g. a
   curation round-trip) but never subtracts the standing ones.
2. **Every goal run cites its brief.** The brief carries intent, boundaries, and definition
   of done; the prompt carries the checkable condition. No freestanding goals.
3. **Fresh-context review — one pass, by Fable.** Substantive slices get a single
   fresh-context Fable review of the full diff against the brief and CLAUDE.md's invariants
   before being called done (the `reviewer` agent). This is independent judgment on a
   finished diff — a session must NOT stack extra self-verification passes, re-run gates it
   already ran green, or spawn workhorse agents to re-check itself. Run the real gates once,
   then hand the diff to Fable. Trivial mechanical work seals without a review.
4. **Lessons compound.** `LESSONS.md`, one lesson per entry. When a loop iteration fails,
   fix the instance *and* encode the fix into the skill or brief so every future iteration
   inherits it.
5. **Model tiering** — per the global working agreement: Opus 5 `xhigh` is the workhorse for
   scouting and building (`scout`, `builder`, workflow work stages); **review passes run on
   Fable** (`reviewer`, `finalizer` — never a lower tier). Workflow `agent()` calls pass
   `model` explicitly ("opus" work / "fable" review) since they'd inherit the session model.
6. **Pilot before fan-out.** `--duration 30` before any full sort; a small slice before any
   wide workflow; variant outputs archived, never overwritten (a W2 obligation — until the
   versioned run store lands, protect full sorts from being clobbered by smoke tests).

## Phase map

| Phase | Brief | Loop type | Stop-condition engine |
|---|---|---|---|
| W0 Quick wins | `goals/GOAL_W0_QUICKWINS.md` | one goal run | suite + sort smoke + Pilot journeys |
| W1 Curation | `goals/GOAL_W1_CURATION.md` | goal run per slice | suite + smoke + curation round-trip + report render |
| W2 Reproducibility | `goals/GOAL_W2_REPRO.md` | goal run per slice | regenerate-from-record check + suite |
| W3 The face (Ben picks) | `goals/GOAL_W3_FACE.md` | **Ben veto gate**, then slices | Ben's pick; then per-slice journeys |
| W4 Multi-recording | `goals/GOAL_W4_MULTI.md` | goal run per slice | batch smoke on ≥2 file sets + suite |
| WD Lab deployment | `goals/GOAL_WD_DEPLOY.md` | turn-based, lab-box sessions | install + sort + report proven on the lab box |

Sequence: W0 → W1 → W2 → W3 → W4, with WD alongside whenever lab-box access exists. W3 does
not start until Ben picks the face (and ideally after the lab requirements pass — see
NORTHSTAR open questions).

## Prompt templates (the live filled-in queue lives in ROADMAP.md)

Start sessions from this repo's root so CLAUDE.md, the agents, and the skills load. Prompts
are plain, self-contained Fable prompts authored with the `fable-prompt-builder` skill: open
with intent, then the task, verifiable done-criteria, hard boundaries, and close with "seal
per the between-run contract" (CLAUDE.md). Never bolt on generic "verify your work" lines —
the gates and the review pass already cover that.

**A phase/slice run:**
```
<Intent: who this serves and what it unlocks.> Execute goals/GOAL_<X>.md (slice N if
sliced). Done when: <the brief's checkable conditions, with the gates named>. Boundaries:
<the brief's>. Seal per the between-run contract.
```

**Babysit (only when a multi-hour run actually exists):**
```
/loop 15m check the running sort/sweep: append progress to the run's notes, flag a stalled
phase. Restart at most twice; on a third stall stop the loop and report what's wrong. Stop
when it completes.
```

## What this file is not

Not a place for product decisions (NORTHSTAR.md) or per-phase detail (the briefs). When a
loop stalls or overreaches, the fix lands here or in a skill — that is how the system
improves.
