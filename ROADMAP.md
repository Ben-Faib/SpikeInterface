# ROADMAP.md — the live build queue

*The one place to look for what runs next. Layout: **the NOW box first** — read it and you
know today's move without scrolling; then the dependency graph, the queue at a glance, the
full paste prompts, and the sealed record (provenance) at the bottom. Prompts are paste-ready
**plain Fable prompts**, each run in a fresh session started from this repo's root. Method
lives in `LOOPS.md`; per-track intent in `goals/`; product decisions in `NORTHSTAR.md`; the
design authority for all D work is `DESIGN_UX.md`. Update this file whenever work seals — a
stale status marker, a stale constant inside a prompt, or a stale NOW box is a defect; fix
it on sight. Author new prompts with the `fable-prompt-builder` skill.*

**The arc:** overhaul the surfaces against the D0 spec (accessible, uncluttered, timely)
with the T track making the change reviewable — while the M track deepens the science
(metrics → curation → reproducibility) and the P track generalizes probes for a lab whose
setups differ. Then the face (W3, Ben's pick), then breadth (W4). WD (the lab's Windows+GPU
box) runs alongside everything.

---

## ▶ NOW — updated 2026-08-18 evening: **THE AUTONOMOUS RUN IS ON** (sealing sessions: update this box FIRST)

- **The autonomous run's first wave is SEALED (evening of 2026-08-18):** D1 dashboard
  (`18a5279`, Fable review fix-first → all 7 findings fixed incl. the 80×24 layout
  starvation), D2 engine half (`fc19579`, protocol elapsed/phase_done/result, review
  ship), P1 probe import (`384884e`, peer session, review ship) — on top of the
  morning's T1 + M1. Suite: 344 green.
- **Next in dependency order:** D2 view half (progress modal renders the new timing +
  result cards; the modal-contract change is pre-agreed in DESIGN_UX §3), then D3
  report (+ its progress plumbing), D4 flow modals, B1 (now unblocked — D1 released
  SpikeInterface_Menu.py). P1 handoffs are already routed (editor guard shipped in D1;
  P3 items recorded in the brief).

## The dependency graph

```
  D0 spec (drafted) ──veto──► D1 dashboard ────► D4 flow modals
        │                     D2 run experience
        │                     D3 report ◄─────── M1 metrics (ready now)
        │                                            │
  T1 harness (SEALED ✓) ─────baselines/contracts──► D1 D2 D3        M1 (SEALED ✓) ──► W1 curation ──► W2 repro
        └────────────────► T2 journey refactor + T3 honesty states         (W1 slice 4 TUI triage
                              (after D1/D2)                                  inherits DESIGN_UX §1)

  P1 probe import (ready now) ──► P2 multi-shank ──► P3 wiring verify (needs adapter map)
                                                          (P menu-UI portions after D1)

  W3 face (Ben's pick, after D track) ──► W4 multi-recording (last; needs W1+W2+lab data)
  WD lab deployment: standing track, any time lab-box access exists
```

## The queue at a glance

| # | Item | Brief | State |
|---|---|---|---|
| — | T1 testing harness | `goals/GOAL_T_TESTING.md` | **SEALED 2026-08-18** (peer, `6171816`) |
| 1 | M1 widen quality metrics | prompt below (was W0 item 5) | **SEALED 2026-08-18** |
| 2 | P1 probeinterface import | `goals/GOAL_P_PROBES.md` | **SEALED 2026-08-18** (peer, `384884e`) |
| 3 | D0 veto | `DESIGN_UX.md` | **APPROVED 2026-08-18** |
| 4 | D1 dashboard | `goals/GOAL_D_UIUX.md` | **SEALED 2026-08-18** (`18a5279`) |
| 5 | D2 run experience | `goals/GOAL_D_UIUX.md` | **SEALED 2026-08-18** both halves (`fc19579` + view); D2b manifest follow-up filed |
| 6 | D3 report | `goals/GOAL_D_UIUX.md` | **SEALED 2026-08-18** (`d12ff5c`; visual pass = Ben opening it) |
| 7 | D4 flow modals | `goals/GOAL_D_UIUX.md` | **SEALED 2026-08-18** (`f115015`) |
| 8 | T2/T3 journey + honesty tests | `goals/GOAL_T_TESTING.md` | **SEALED 2026-08-18** (peer, `7e6938d`) |
| 9 | P2 multi-shank · P3 wiring | `goals/GOAL_P_PROBES.md` | after P1; P3 needs adapter map |
| 10 | W1 curation | `goals/GOAL_W1_CURATION.md` | **slice 1 SEALED 2026-08-18** (rule owner); slices 2-4 (curation loop, Phy, triage) READY — Ben chose this path |
| 11 | W2 reproducibility | `goals/GOAL_W2_REPRO.md` | after/with late W1 |
| 12 | W3 face | `goals/GOAL_W3_FACE.md` | gated: Ben's pick, after D track |
| 13 | W4 multi-recording | `goals/GOAL_W4_MULTI.md` | gated: W1+W2+lab data |
| — | WD lab deployment items 1–4 | `goals/GOAL_WD_DEPLOY.md` | gated: lab-box access |
| B1 | BUG: bare `report` action crashes | prompt below | **SEALED 2026-08-18** (peer, `b43869e`) |
| E1 | Explore overhaul: same-clock view + honest labels (Ben flag, 2026-08-19) | **SEALED** — and it surfaced: **channel 1 is pathological** (pure oscillation, inside the CMR) → first target for the queued bad-channel/preprocessing slice | **SEALED 2026-08-19** |
| C1 | NEV online-vs-sorted comparison (Ben, 2026-08-18 eve) | engine **SEALED** (`39ca919`) — FINDING: the original .nev has ZERO online-sorted units | **SEALED** |
| C2 | Manual-sort comparison (`--nev`/`--delta-ms`, containment column) | **SEALED** (`4ffcfda`) — all 7 manual units 97-100% contained in tdc2's merges; ~0.6 ms crossing-vs-peak offset measured | **SEALED 2026-08-18** |
| D5 | Actions-first main screen (Ben, 2026-08-18 late) | NORTHSTAR decision of record | **SEALED 2026-08-18** (`63fe05c`) |
| D3b | report/compare progress plumbing — §6's last piece (Ben re-confirmed 2026-08-18 eve) | `DESIGN_UX.md` §6 | **SEALED 2026-08-18** (`a1907b5`) |

## Paste prompts, in run order

### M1 — widen the quality metrics  [SEALED 2026-08-18 — prompt kept for provenance]

```
The workbench's unit-quality evidence is 3 of SpikeInterface's ~20 metrics while the PCA the
isolation metrics need is already computed and thrown away — every downstream surface (the
report's quality section, the coming D3 verdict tiles, W1's curation thresholds) flatters
thin evidence until this widens.

Widen the computed quality metrics in scripts/run_sorting.py (the metric_names list, line
~1054): add presence_ratio, amplitude_cutoff, amplitude_median, and the PCA-based isolation
metrics (isolation_distance, l_ratio, d_prime, nn_hit_rate). Confirm the report's quality
table renders the new columns and degrades gracefully for old saved analyzers that lack
them.

Done when: the suite is green; the 30 s sort smoke passes with the noise-floor canary at
~4 µV; a fresh analyzer carries the new columns; the report renders them; and a
fresh-context Fable review of the diff has run with findings addressed or recorded.

Boundaries: metrics stay non-fatal (the Sorting saves first; a metrics crash degrades to
success-with-note and cleans up half-built derived files); no threshold/curation logic (W1
slice 1's job); no UI changes beyond the report's existing table rendering what the
analyzer has. Seal per the between-run contract.
```

### P1 — probeinterface import  [SEALED 2026-08-18 — `384884e`]

```
The UPitt researchers' probes have different setups, and today the workbench only knows its
built-in profiles plus hand-entered ones — a probe the lab already has a probeinterface
description for should drop straight in.

Execute goals/GOAL_P_PROBES.md slice P1: import probeinterface .json (and .prb where
probeinterface reads it) into the user probe library via CLI and menu, validated against
the recording's neural channel count with honest errors naming any mismatch.

Done when: the suite and loader smoke are green; a 30 s sort runs end-to-end with an
imported probe applied and the report's probe section renders it faithfully; the canary
holds at ~4 µV; explicit-probe-fails-hard / default-falls-back-soft asymmetry is preserved;
and a fresh-context Fable review has run with findings addressed or recorded.

Boundaries: probes.py stays the single owner of geometry; geometry still only soft-re-ranks
sorters; test probes are built in-test, never committed fixtures; keep menu-side UI touches
minimal (the real probe-UI pass follows D1). Seal per the between-run contract.
```

### D1–D4 — the overhaul slices  [gated on the D0 veto]

Authored with `fable-prompt-builder` **when Ben's veto lands**, against the spec as amended
— pre-writing them risks quoting a spec line the veto changes. Each will cite
`goals/GOAL_D_UIUX.md` + the spec sections from DESIGN_UX §7, name the T1 gates
(deliberate snapshot re-baselining with reviewed diffs), and seal per the contract.

### B1 — bare report action crashes  [SEALED 2026-08-18 — `b43869e`]

```
A documented invocation is a crash: `uv run python scripts/make_report.py` (and
`SpikeInterface_Menu.py report`) with no --sorter dies with a TypeError at
SpikeInterface_Menu.py:109 — _analyzer_dir joins a None sorter (reproduced 2026-08-18 on
unmodified code). Since a bare non-TTY launcher run silently dispatches the report action,
check whether piped/CI invocations hit the same path.

Fix the default-sorter resolution for the report action (the active/recommended sorter, or
the only saved sort, with an honest error naming the fix when nothing is saved), and add a
regression test for the bare invocation. Done when the bare command builds the report on
this repo's saved sort, the no-saved-sort case errors honestly instead of crashing, and the
suite is green. Boundaries: resolution logic only — no report content changes. Seal per the
between-run contract.
```

### T2/T3, P2/P3, W1+ — authored when their gates clear

Same rule: fresh prompts from the briefs at gate-time, constants verified against source.

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

- **2026-08-18 — T1: the testing harness (peer session, `6171816` + `4ba6205`).** Eight
  deterministic SVG snapshot baselines of today's dashboard + modals
  (pytest-textual-snapshot), a fresh-build structural golden check for the report
  (section order pinned in `REQUIRED_SECTION_ORDER` — D3 edits that baseline in its
  commit), contract tests locking the sort-progress protocol (SHAPES table gates new
  event types; optional keys on existing events flow free; `done`/`error` stay as-is),
  and `tests/README.md`'s deliberate re-baselining procedure. Suite 302 green in ~30 s.
  Fable review: 7 findings, none blocking, six folded in pre-seal; LESSONS S4 recorded
  (Windows-safe subprocess text capture). Also produced the 10-finding DESIGN_UX
  feasibility critique (`a11b259`).
- **2026-08-18 — M1: quality metrics widened, 3 → 12 columns.** Dependency extensions
  (spike_amplitudes, principal_components) now compute *before* quality_metrics,
  best-effort — a dependency failure drops only its metrics, surfaced on both output
  channels, never the phase. New columns: presence_ratio, amplitude_cutoff,
  amplitude_median, isolation_distance, l_ratio, d_prime, nn_hit_rate, nn_miss_rate.
  Report renders whatever the analyzer has (old sorts degrade gracefully), NaN as an
  honest "–" that sorts to the bottom, with a degenerate-PCA caveat. Gates: 301 tests
  green, smoke canary 4.077/3.975 µV, `--progress json` purity re-proven (46 lines, 0
  leaks, strict-JSON nulls). Fable review: **ship** (4 low findings, all folded in).
  *Notes for W1 slice 1:* presence_ratio quantizes to {0,½,1} at 132 s with 60 s bins —
  consider `bin_duration_s≈15`; consider blanking isolation_distance where l_ratio is NaN.
- **2026-08-18 — overhaul kickoff** (this session). Ben's directive taken on record
  (NORTHSTAR updated: UPitt researchers, varied probe setups, Faibussowitsch × Al-Olimat,
  UI/UX mandate); `DESIGN_UX.md` D0 spec drafted from screenshots of every surface; GOAL_D /
  GOAL_T / GOAL_P briefs written; W0 dissolved into the graph; T1 dispatched to the peer
  session; queue restructured as a dependency graph.
- **2026-08-18 — orchestrator installed** (`4e60ec2`). NORTHSTAR/LOOPS/goals/ROADMAP/SEALS/
  LESSONS + 4 agents + verify-spike & status skills, patterned on decantv2; W0 brief
  verified against source (two of seven audit quick wins already landed: Explore opens its
  figures, sort stderr goes to a per-run log).
- **Pre-orchestrator landings** (provenance, from git): probe geometry real + menu probe
  manager (PR #1, 2026-06); array/yield metrics + legible failures + channel/probe views
  (`4807ce0`); download telemetry + deep image delete (`dd71a3d`); Windows Docker-sort
  cleanup crash fixed + Explore shows data (`7940f96`, 2026-08-18); CLAUDE.md rewritten
  against source (`49dd4a3`).
