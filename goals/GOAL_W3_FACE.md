# GOAL W3 — The face: one audience/medium bet, Ben's pick

## Intent

With a trustworthy (W1) and reproducible (W2) core, the workbench chooses who it serves.
The audit offers three largely mutually exclusive bets — each a major UI surface with its own
test harness — and the arc commits to exactly one:

- **Guided Sort wizard** (WORKBENCH_DIRECTIONS.md §Path 3) — for onboarding lab members who
  know neuroscience but not SpikeInterface/Docker/metrics.
- **Spike Live web** (§Path 5) — for people who reason by eye and share links: zoom, pan,
  lasso clusters, zero install.
- **Terminal Power IDE** (§Path 6) — for fluent users living on SSH/HPC terminals.

## Gate — this brief is not runnable yet

**Ben picks the face**, ideally after the lab-requirements pass (NORTHSTAR open questions:
who the users are, their fluency, where the pain is). The pick is a decision of record for
NORTHSTAR.md. Until it lands, no session starts W3 work.

## When the pick lands

Rewrite this brief around the chosen path's WORKBENCH_DIRECTIONS section: slice it (each
slice a goal run with a journey-based done-check via `verify-spike`), carry the honesty and
view/controller boundaries, and add the paste prompts to ROADMAP.md.

## Boundaries that hold regardless of pick

- Built on W1+W2's core — the face surfaces curated, provenance-carrying results; it never
  grows its own metrics or run store.
- One face. Effort split across two of these bets is the named failure mode.
- Windows-first verification for anything the lab will touch.
