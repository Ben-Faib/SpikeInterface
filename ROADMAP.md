# ROADMAP.md — the live build queue

*The one place to look for what runs next. Layout: **the NOW box first** — read it and you
know today's move without scrolling; then the queue at a glance, then the full paste prompts
in run order, then the sealed record (provenance) at the bottom. Prompts are paste-ready
**plain Fable prompts**, each run in a fresh session started from this repo's root. Method
lives in `LOOPS.md`; per-phase intent in `goals/`; product decisions in `NORTHSTAR.md`.
Update this file whenever work seals — a stale status marker, a stale constant inside a
prompt, or a stale NOW box is a defect; fix it on sight. Author new prompts with the
`fable-prompt-builder` skill.*

**The arc:** deepen and harden one recording (W0 quick wins → W1 curation → W2
reproducibility), then one face (W3, Ben's pick), then breadth (W4 multi-recording) — with
WD (the UPitt lab's Windows+GPU box) as a standing track alongside. Full rationale:
NORTHSTAR.md; source analysis: WORKBENCH_DIRECTIONS.md.

---

## ▶ NOW — updated 2026-08-18 (sealing sessions: update this box FIRST)

- **Next build move: run the W0 prompt below.** Five audit quick wins remain (verified
  against source 2026-08-18); everything later builds on them.
- **Needs Ben (OPEN in SEALS.md):** ratify the NORTHSTAR arc (or amend it); the lab
  requirements pass (what Tracy's lab needs first — shapes W3 and could reorder W1/W4);
  lab-box access for WD.
- **Orchestrator installed 2026-08-18** — NORTHSTAR / LOOPS / goals / SEALS / LESSONS /
  agents (scout·builder·reviewer·finalizer) / skills (verify-spike, status), patterned on
  decantv2. Sessions seal per the between-run contract in CLAUDE.md.

## The queue at a glance

| # | Item | Brief | State |
|---|---|---|---|
| 1 | W0 quick wins (5 remaining) | `goals/GOAL_W0_QUICKWINS.md` | **READY — paste prompt 1** |
| 2 | W1 slice 1: defensible auto-curation | `goals/GOAL_W1_CURATION.md` | ready after W0 |
| 3 | W1 slices 2–4: curation loop, Phy, TUI triage | `goals/GOAL_W1_CURATION.md` | after slice 1 |
| 4 | W2: versioned runs + provenance + regenerate | `goals/GOAL_W2_REPRO.md` | after/with late W1 |
| 5 | W3: the face | `goals/GOAL_W3_FACE.md` | **GATED — Ben's pick** |
| 6 | W4: multi-recording | `goals/GOAL_W4_MULTI.md` | GATED — W1+W2 + lab data |
| — | WD: lab-box deployment items 1–4 | `goals/GOAL_WD_DEPLOY.md` | GATED — lab-box access; runs alongside any phase |

## Paste prompts, in run order

### 1 — W0 quick wins  [READY]

```
This workbench is becoming the tool Tracy's UPitt lab uses to turn raw Blackrock recordings
into publishable single units, and five small audit-identified dead-ends still undercut the
trust it needs first: a 0-unit sort shows green success, the INSPECTING panel clips its own
text, the active sorter forgets itself every launch, the keyboard help lies, and quality
metrics are 3 of ~20 while the PCA they need is computed and thrown away.

Execute goals/GOAL_W0_QUICKWINS.md — all five remaining wins, at their stated scope.

Done when: the suite is green; the 30 s sort smoke passes with the noise-floor canary at
~4 µV; a deliberate 0-unit sort shows the amber detect_threshold hint in the UI; the
INSPECTING panel shows its full content; a relaunch restores the previously active sorter;
the help names only real bindings; the new metric columns appear in a fresh analyzer and the
report renders them; and a fresh-context Fable review of the full diff has run with its
findings addressed or recorded.

Boundaries: no adjacent refactors; the SNR≥5 headline rule stays (W1's job); CLAUDE.md's
invariants — aux-drop ordering, the µV gate, --progress json stdout purity, non-fatal
metrics — are untouchable; update CLAUDE.md's .si_menu.json key list when you persist the
active sorter. Seal per the between-run contract.
```

### 2 — W1 slice 1: defensible auto-curation  [after W0 seals]

```
The workbench's headline "N of M look high-quality" rests on a hardcoded SNR≥5 &
ISI≤0.5 rule that can mislead the lab members who trust it most; with W0's widened metric
base landed, the count can finally mean something defensible.

Execute goals/GOAL_W1_CURATION.md slice 1: replace the hardcoded rule with a configurable,
literature-grounded threshold rule owned in one place, its thresholds stated wherever the
count appears.

Done when: the suite and the 30 s sort smoke are green (canary ~4 µV); every surface that
shows the count states its rule; the rule is configurable and its config persists; and a
fresh-context Fable review has run with findings addressed or recorded.

Boundaries: the brief's — one owner for the rule, no curation-lifecycle work yet (that is
slice 2), no changes to how metrics are computed. Seal per the between-run contract.
```

### 3+ — W1 slices 2–4, W2 slices  [author when their turn comes]

Written fresh from `GOAL_W1_CURATION.md` / `GOAL_W2_REPRO.md` with `fable-prompt-builder`
when the preceding slice seals — constants and file:line anchors go stale too fast to
pre-write them. Keep each prompt: intent → slice → done-criteria naming the gates → brief's
boundaries → seal.

### WD items  [when lab-box access exists]

Authored per `goals/GOAL_WD_DEPLOY.md` items 1–4 when Ben has a session on (or remote access
to) the lab box. Item 1 (fresh-clone install) and item 2 (full journey on Windows) can run
the same day.

## Rules for this file

1. **Keep it true.** A sealing session updates the NOW box, marks its queue row, moves the
   item to the sealed record with date + one-paragraph result, and refreshes any constant a
   later prompt quotes.
2. **Prompts are plain, self-contained Fable prompts** — intent first, never a bare task; no
   generic "verify your work" bolt-ons (the gates and the review pass in LOOPS.md already
   cover it). Sealed items keep their original prompts for provenance.
3. **Conditional behavior goes in the prompt, not in a global rule** — what matters for one
   item is written into that item's prompt, unconditionally.

## Sealed record

- **2026-08-18 — Orchestrator installed** (this session). NORTHSTAR/LOOPS/goals/ROADMAP/
  SEALS/LESSONS + 4 agents + verify-spike & status skills, patterned on decantv2; W0 brief
  verified against source (two of seven audit quick wins already landed: Explore opens its
  figures, sort stderr goes to a per-run log).
- **Pre-orchestrator landings** (provenance, from git): probe geometry real + menu probe
  manager (PR #1, 2026-06); array/yield metrics + legible failures + channel/probe views
  (`4807ce0`); download telemetry + deep image delete (`dd71a3d`); Windows Docker-sort
  cleanup crash fixed + Explore shows data (`7940f96`, 2026-08-18); CLAUDE.md rewritten
  against source (`49dd4a3`).
