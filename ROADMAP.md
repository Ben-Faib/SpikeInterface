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

## ▶ NOW — updated 2026-08-18 night: **CONDUCTOR RUN CLOSED MID-FLIGHT (Ben: limit) — re-enter with THE CONDUCTOR v2 prompt below**

- **Sealed this run:** P2 (peer `8af8111`) · PRE1 (`c823f55`, premise re-scoped:
  zero bad channels in-band; tdc2 non-determinism 14/16/18 measured) · D6 (peer
  `98f2645`) · DEBT (`0127dac`, extra-.nev latent bug fixed). Main `c580286`,
  suite 459 green at close.
- **Parked on branches (verify tips before building):** W1 s2
  `worktree-agent-ace3305ebf35c6b78` — review fold COMPLETE at `c1af408`, worktree
  suite 425 green, needs rebase + fresh end-to-end validation only; W1 s3
  `lane-w1s3` (stacked on s2's `314dc85`; worktree was in session scratchpad —
  the BRANCH is the persistent artifact; handoff commit requested, unconfirmed);
  W2 `worktree-agent-a660e788ee8453c5b` — handoff commit `467ed7e`: store +
  provenance done and exercised, regenerate written-never-run, tests missing;
  no review yet.
- **Peer session** (if still open) holds W1 s4, gated: starts only when a conductor
  confirms s2 is on main. Gated OPEN: P3 (adapter map), WD (lab box), W3 (face
  pick), W4 (lab data).

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
| 9 | P2 multi-shank · P3 wiring | `goals/GOAL_P_PROBES.md` | **P2 SEALED 2026-08-18** (peer, `8af8111`: ProbeGroup imports as probes-as-shanks, wiring pinned verbatim, physical density classing; suite 388 green, canary 3.993 µV, review ship). P3 needs adapter map; three new recorded items in the brief |
| 10 | W1 curation | `goals/GOAL_W1_CURATION.md` | **slice 1 SEALED 2026-08-18** (rule owner); **slice 2 IN FLIGHT** (worktree lane); slices 3-4 launch on s2's record schema |
| 11 | W2 reproducibility | `goals/GOAL_W2_REPRO.md` | next after PRE1 lands (run_sorting freed) |
| PRE1 | bad channels out of the reference (E1's finding; conductor prompt item 1) | prompt below | **SEALED 2026-08-18** (`c823f55`) — **premise re-scoped with evidence**: zero channels flagged; ch1's pathology is sub-300 Hz (bandpass removes it pre-CMR; in-band it's the QUIETEST channel and carries a unit); feature kept as insurance + measured tdc2 non-determinism (14/16/18 units) now drives W1 anchoring + W2 tolerances |
| D6 | the airy dashboard (Ben's two mocks, approved in-session) | NORTHSTAR decision 2026-08-18 night | **SEALED 2026-08-18** (peer, `98f2645`) — hairline sections, crest ≥34 rows, pressable t-chip, key chips, air-yields-first; review fix-first (hairline never painted; resize-under-modal), all folded; suite 441, deliberate double re-baseline |
| DEBT | recorded-debt bundle: report headers · D2b manifest · label home · dead code · extra-.nev | conductor prompt item 6 | **SEALED 2026-08-18** (`0127dac`) — all five closed; extra-.nev was a REAL latent bug (discovery by sort-order luck → now prefers-data + honest ambiguity refusal, one sealed test deliberately flipped); review ship, findings 1-4 folded; recorded: th-padding dead-click cosmetic |
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

### THE CONDUCTOR v2 — re-entry: land the parked lanes, finish the queue  [READY — paste into a fresh session]

```
The UPitt researchers in Tracy's lab need this workbench to take raw Blackrock
files to curated, defensible single units. The first conductor run sealed P2,
PRE1, D6 and DEBT (main c580286, suite 459 green) and closed mid-flight at Ben's
request with three lanes parked on branches. You are the conductor continuing it:
land the parked lanes, finish the queue, close the run.

Re-enter from the board, never from memory: CLAUDE.md's Orchestration read order,
SEALS.md for where things stand. Keep ROADMAP true as you go. Facts of record
that bind design (measured, sealed): E1's "ch1 poisons the reference" premise is
FALSE in the sort band (PRE1 measured it; detection kept as insurance, zero
excluded here), and tridesclous2 is NON-DETERMINISTIC on this recording
(14/16/18 units across identical runs) — curation records hard-anchor to their
sort and no reproduction criterion may use unit counts/ids.

The queue, dependency-ordered — verify each branch tip before building on it
(LESSONS S5: state and check the expected base; close-time handoff commits were
requested but not confirmed):

1. LAND W1 s2 (curation lifecycle) from branch worktree-agent-ace3305ebf35c6b78
   (worktree .claude/worktrees/agent-ace3305ebf35c6b78, data symlinked). Its
   fix-first Fable review is FULLY FOLDED at tip `c1af408` (stacked on `314dc85`;
   both blockers + anchor rider + unit_id_map/add_label-source schema adds +
   stale marker + pair-mode error + summary-try split + preferred_analyzer
   one-home + repo-relative paths + the restated unreachability claim: residue
   3.6-5.4×, any within-unit split returns residue-swamped children, leverage
   upstream). Worktree suite 425 green post-fold, but NO end-to-end re-validation
   ran after the fold — the apply path changed, so yours is the authority.
   Remaining: rebase onto main, suite + 30 s smoke + canary, run the full
   validation chain fresh (main-tree sort → record → apply → curated re-score
   canary → compare --nev PFCM7_d0ephys_Block2_manuallySorted.nev; records
   anchor to THAT sort), add CLAUDE.md's curation.py ownership row + commands
   line, seal. Record as follow-ups: run_sorting seam promotion (public
   analyzer-build+metrics fn), curation.py import-gui (sigui ingestion — an
   explicit scope shift off slice 2), seeded 3-way GMM as an optional split
   method (reviewer-measured incremental, not implemented).
2. LAND W1 s3 (Phy export) from branch lane-w1s3 (stacked on s2's pre-fold
   314dc85; its worktree lived in session scratchpad — the branch is what
   persists; recreate a worktree if the dir is gone). Read its HANDOFF; rebase
   onto s2's folded tip, finish per its brief (export half: structural
   verification, curated-supersedes-raw with force-raw flag; round-trip half:
   Phy labels back through curation.py's API keyed via the id map, source="phy",
   anchor honored, collision rule stated), Fable review (none run yet), fold,
   integrate behind s2, seal.
3. OPEN THE s4 GATE: the peer session (spikeinterface-28, if open) holds W1 s4
   in-TUI triage, fully scoped in its message log — ping it the moment s2 is on
   main; if no peer, run it as a builder lane: unit list + per-unit metrics card,
   g/m/n/u labels writing the SAME record through curation.py's pure-Python API
   via the controller Protocol (view imports no SI), reviewed n/N + stale
   legible, D6's DESIGN_UX §2 language + §1 binding, deliberate snapshot
   baselines, Pilot journeys for label→persist→relaunch. Fable review, seal.
4. LAND W2 (reproducibility) from branch worktree-agent-a660e788ee8453c5b, tip
   `467ed7e` — its commit-message HANDOFF is the authority. Honest state: store
   (slice 1) + provenance (slice 2) DONE and exercised live (four coexisting tdc2
   runs, a real refused smoke-clobber with the incumbent pinned, canaries
   3.938-4.142); regenerate/compare_runs/match-report (slice 3) CODE WRITTEN
   NEVER RUN; config export (slice 4) drafted, unrun; TESTS NOT WRITTEN — the
   largest gap. Its own next-steps list is correct: re-run the suite (an edit
   postdates the last run), first-run the regenerate command and calibrate
   CONTAINMENT_MIN/METRIC_REL_TOL against measured numbers, render report +
   compare through the store, write the missing tests (pointer/no-clobber/
   legacy/provenance/containment; store functions are injectable), decide
   keep-or-drop on slice 4. Known risk it names: a sorter-crash run leaves a
   run dir with no run_info.json — list_runs skips them, nothing prunes.
   Then Fable review (regenerate criteria must respect the non-determinism
   evidence), fold, integrate LAST of the code lanes — at this integration
   re-plumb curation.py's sort_paths() seam (and s3/s4's uses) through the
   store, wiring records + curated outputs inside run dirs (the store already
   reserves them there). Seal.
5. CLOSE THE RUN: final full suite on main; a real launch check
   (run-spikeinterface skill); a closing board pass — ROADMAP rows, SEALS block,
   pinned lines, and the OPEN items exactly four, each with its one-line
   unblock: P3 (adapter map), WD (lab-box access), W3 (face pick), W4 (lab
   recordings). Never fake progress on those four.

Method unchanged and already law: builders on Opus, reviews on Fable, one
fresh-context review per substantive slice with findings folded or recorded;
parallel lanes only with explicitly disjoint file sets, explicit-path commits
(the tree can carry a peer's uncommitted work — never git add -A); CLAUDE.md's
Invariants that bite bind every edit (µV double-scaling gate, ~4 µV canary as a
verdict, aux-AND-bad-channels drop before CMR, stdout purity, view imports no
SI); raw data never enters git or leaves the machine; a queue item whose premise
fails gets re-scoped on the board with the evidence; ask Ben only what is
genuinely his, batched in SEALS OPEN. If this run also stops short, seal partial
state per the between-run contract — this prompt pattern continues from the
board.
```

### THE CONDUCTOR (v1) — original queue-to-completion prompt  [SUPERSEDED by v2 above — kept for provenance]

```
The University of Pittsburgh researchers in Tracy's lab need this workbench to take
their recordings from raw Blackrock files to curated, defensible single units on
their own machine. Last night's 19 sealed slices proved the machinery and settled
the direction: the sorter finds 97-100% of every manually sorted unit's spikes but
merges what a human splits, so Ben chose the curation path. You are the conductor
for the remainder — every unblocked item on the board, sealed to the standard those
19 met.

Re-enter from the board, never from memory: CLAUDE.md's Orchestration section gives
the read order (NORTHSTAR → LOOPS → the active goals/ brief → ROADMAP's NOW box;
DESIGN_UX for any UI surface; SEALS.md for where things stand). Keep ROADMAP true
as you go — a stale marker is a defect.

The queue to completion, dependency-ordered:
1. PRE1 — bad channels out of the reference. E1's same-clock view showed channel 1
   is pathological (pure oscillation) and it currently sits inside the common
   median reference every other channel is subtracted against. Detect bad channels,
   exclude them from the reference in the sort pipeline, state the exclusion in
   provenance and the report, then re-run the full tridesclous2 sort and the
   manual-.nev comparison to MEASURE what it bought.
2. W1 slice 2 — the curation loop (goals/GOAL_W1_CURATION.md): merge/split/label
   decisions saved, applied to a curated Sorting, metrics re-scored, surfaces
   honest about curated-vs-raw. Its validation reference is
   PFCM7_d0ephys_Block2_manuallySorted.nev: done means splitting tdc2's ch5/ch7/ch9
   merges can reproduce the manual units.
3. W1 slices 3 and 4 in parallel lanes — Phy export, and the in-menu unit triage
   (DESIGN_UX §1 language binds the menu surface).
4. W2 (goals/GOAL_W2_REPRO.md) — versioned runs, complete provenance,
   regenerate-from-record; overlap it with W1 s3/s4 only where file sets are
   disjoint.
5. P2 multi-shank probes (goals/GOAL_P_PROBES.md) — a parallel lane any time.
6. The recorded-debt bundle, one lane: keyboard-sortable report headers, the D2b
   pending-phase manifest, online_unit_labels relocating to blackrock_io,
   controller dead code (cycle_active and friends), and robustness for extra .nev
   files beside the recording set.

Done when: every item above is SEALED — gates green per the verify-spike skill
(the ~4 µV noise-floor canary is a verdict), one fresh-context reviewer-agent pass
per substantive slice with findings folded or recorded, board and SEALS updated
per the between-run contract — and a final full-suite run plus a real launch check
pass. P3, WD, W3 and W4 stay gated on Ben's inputs (the adapter map, lab-box
access, lab recordings, the face pick): leave each OPEN in SEALS with one line on
what unblocks it, and never fake progress on them.

Method that is already law here: builders run on Opus, reviews on Fable; parallel
lanes get explicitly disjoint file sets and commit their own paths (the way
T1/P1/B1 ran — a peer session, if one is open, takes well-bounded lanes);
CLAUDE.md's Invariants-that-bite bind every edit; raw data never enters git or
leaves this machine. Don't redesign sealed surfaces except where a queue item says
so. A queue item whose premise turns out wrong gets re-scoped on the board with
the evidence, not silently skipped. Ask Ben only for decisions that are genuinely
his, batched in SEALS OPEN, and keep building on other lanes meanwhile.

You have ample time and context. If the run stops short anyway, seal partial
state per the between-run contract — this same prompt re-entered in a fresh
session continues from the board.
```

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
