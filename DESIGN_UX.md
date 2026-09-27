# DESIGN_UX.md - the workbench design spec (D0)

*Drafted 2026-08-18 from Ben's overhaul directive and screenshots of every surface (dashboard,
sort-progress modal, sort-how-much modal, the HTML report, spikeinterface-gui). **Ben veto
gate: nothing in D1–D4 is built until Ben approves or amends this spec.** Section §7 maps
spec → implementation tasks. The peer session's feasibility critique
(`docs/design/DESIGN_CRITIQUE_2026-08-18.md`, 10 findings) was folded in the same day -
the spec below is the post-critique version, ready for the veto. **§2 now
summarises Spike 2.0 (2026-09-27, `goals/GOAL_V2.md`)**, which replaced the F2 dashboard.*

Ben's brief, verbatim goals: more accessible · less clutter · focused on what matters ·
clean, with clarity, good spacing and hierarchy, ample room · the UX feels like the program
provides **timely updates and results**.

---

## §1 Design language (binds every surface)

1. **One fact, one place.** A fact appears in exactly one home per screen. Today the active
   sorter is stated four times on the dashboard at once (SORT banner row, ACTIVE chip in the
   list, INSPECTING header, footer "Active sorter:"). The banner is the home; everything
   else marks it structurally (position, bold, left-bar) without restating it.
2. **Signal budget: at most two marks per list row at rest.** Today a sorter row can carry
   five (`★ · name · 16u · ✓fits · ✓ready`). Rows show name + one availability glyph +
   unit count if a sort is saved; fit/ready/tuning detail appears in INSPECTING for the
   row under the cursor. The cursor is the detail-request gesture.
3. **Hierarchy by weight, not by more chrome.** Three tiers everywhere: primary (bold/
   accent - the thing to look at or do next), normal, secondary (dim - provenance, hints).
   Anything that would be a fourth tier gets cut or moved behind the cursor/a fold.
4. **Ample room.** Panels get inner padding (1 cell TUI / generous rem in HTML); one blank
   line between groups; no full-width separator rules where a gap does the job. When space
   runs out, chrome yields before content (the existing responsive-yield order stays law,
   as do the never-clip Pilot tests).
5. **Color is a role, never decoration, never the only carrier** (NO_COLOR/mono safety is
   existing culture - keep it). Roles: **accent** = focus & the primary action; **green** =
   verified/passed only; **amber** = needs attention, has a next step; **red** = failure,
   has a log; **dim** = secondary. A green that doesn't mean "verified" is a defect.
6. **Timeliness doctrine.** Anything that takes over ~1 s shows what it is doing (named
   phase), that it is alive (elapsed ticking, spinner/heartbeat), and honest progress
   (determinate bar only when the underlying step reports real fractions - a bar at 100%
   under a still-running step, as the current sort modal shows, is a lie by layout). And
   every run **ends with its result presented**, not a vanishing footer line.
7. **Every dead-end names its next step.** Empty, zero, and error states say what happened
   and the one action that helps ("0 units - lower detect_threshold in Edit parameters").

## §2 The dashboard (Spike 2.0 - spec of record: `goals/GOAL_V2.md`, 2026-09-27)

*History: D1's three panels → D5's six numbered actions → D6's hairline language → F2's one
list of fourteen labelled rows (2026-08-19). Ben's 2026-09-27 "build it" on the v2.0
mockups replaced F2 with the journey rail; F2's full text lives in git history
(`769740b` and earlier). `goals/GOAL_V2.md` is the spec; this section is its summary.*

```
 spike  PFCM7_d0ephys_Block2                     tridesclous2 · run c7184d · curated
 ✓ 1 Data ──── ✓ 2 Probe ──── ✓ 3 Sort ──── ▸ 4 Judge ──── · 5 Apply ──── · 6 Share
   3 streams     16 contacts    16 units      4/16
 ──────────────────────────────────────────────────────────────────────────────────
 Home: NEXT STEP card · WHERE THINGS STAND · RECENT        │ UNITS ON THE PROBE
       (or the stage pane the rail is on)                  │  shank, units at contacts
 status line
  ↵  build the report   s  not now   1-6  stages   /  find   ,  settings   ?  help   q  quit
```

- **The rail is the state.** Six stages, each ✓ done (green, verified) / ! needs you
  (amber, has a next step) / · not started, with a one-line caption; `journey.py` decides.
- **One next step.** Home leads with the single best move (§1.7 made structural); `s` steps
  through the alternatives. It never says "nothing to do" without naming what to open.
- **Every value editable, where it lives.** Probe values on 2 Probe, sorter parameters on
  3 Sort (`e`), everything else on Settings (`,`), each row saying what it affects and its
  default. The Sort pane states every value the next sort will use.
- **Evidence before verdicts.** 4 Judge draws each unit's waveform (neighbouring contacts,
  one µV scale), its spike-interval histogram with the refractory window, and its amplitude
  over the recording, flagged units first.
- **Values reproduce.** Runs (3 Sort `r`, 6 Share) re-run a sort from its recipe and show
  the match report criterion by criterion.
- **Keys**: §1 holds; 1-6 are stages, Esc returns Home and never exits, letters belong to
  one pane and are printed on its key line, destructive actions confirm.

## §3 The sort experience (screenshots: SORTING modal ×2, "Sort how much?")

**Findings.** The phase checklist is the right idea, wrongly finished: it shows only
Read/Preprocess/Sort (save, analyze, metrics - half the pipeline - happen invisibly);
raw sorter internals leak as truncated jargon (`split_clusters with local_feature…`); a
bar reads "100%" while work continues; no elapsed time anywhere; and completion dismisses
to a one-line footer message instead of presenting the result.

**Redesign - the modal is the run's honest narrator, then its results card.**

```
  SORTING tridesclous2 · full recording · elapsed 2:14

   ✓ Read broadband        3.2 s
   ✓ Preprocess            4.1 s
   ▶ Sort                  1:58    clustering peaks (29,355 kept)
   · Save sorting
   · Analyze + metrics

   phase 3 of 5  ▂▂▂▂▂▂▂▂░░░░░░  (bar only when the step reports real progress;
                                   otherwise the spinner + ticking elapsed carry aliveness)
   Esc cancel - kills the whole worker tree
```

On completion the same modal becomes the **result card** (no green-and-gone):

```
  ✓ SORTED · tridesclous2 · full recording · 4:07

    14 units found        noise floor 4.0 µV ✓
    9 pass quality thresholds (once M1 lands; until then: units + canary)
    saved → outputs/tridesclous2/

    ↵ close · 3 build report · 4 inspect in GUI
```

- **0 units is an amber card** with the detect_threshold hint - the false-green dead-end
  dies at the source. **Failure is a red card** with the last stderr lines inline and the
  log path (the log already exists on disk; surface it).
- **Result-card actions are a modal-contract change, named as such** (critique #2): the
  dismissal shape grows an optional `next_action` the app dispatches after the pop -
  report via `DISPATCH`, inspect via the `_self` fresh-process path - and the Pilot tests
  that pin the `(ok, message, changed)` contract are updated deliberately in D2.
- Sub-status lines are **translated where known** (a small mapping from common sorter
  messages to plain phrases), truncated to one line otherwise.
- "Sort how much?" keeps its shape; it gains expected durations from the last run of that
  sorter ("Full recording · ~4 min last time") so the choice is informed. When W2's
  versioned runs land, the destructive warning becomes "previous run is kept".

## §4 The HTML report (screenshot: PFCM7 recording report)

**Findings.** Complete and honest, but a flat wall: eleven equal-weight sections; the
answer a researcher opens it for (how many units, are they any good) is a third of the way
down; provenance is split top and bottom; default-Plotly styling; unstyled tables; a tiny
link-row for navigation.

**Redesign - verdict first, evidence below, one visual system.**

1. **Verdict header**: recording · sorter · date, then four stat tiles - **units**,
   **pass-quality count** (M1's widened metrics are live; the threshold *rule* stays W1's),
   **noise floor**, **window sorted** (with the partial-sort caveat inline when eff <
   total). **The noise-floor tile makes no pass/fail claim** (critique #4): the ~4 µV
   canary is an observed regression signal, not a validated threshold - the tile shows the
   number with its expected band as text ("4.0 µV · expected ≈3.9–4.1 for this rig,
   post-bandpass+CMR"), and only an *outside-band* value turns the tile amber with the
   double-scaling explanation. Never a green ✓ science claim.
2. **Sticky table of contents** (left rail ≥1100 px, collapsing to a top bar below) with
   per-section status glyphs - the current status table becomes navigation.
3. **Sections re-cut in reader order**: 1 Verdict · 2 Sorted units (raster, rates,
   templates) · 3 Quality metrics (table + scatter) · 4 Array & yield · 5 Probe &
   channels · 6 Recording context (LFP, online .nev units, events - demoted: it's input
   context, not results) · 7 Provenance (status table + About merged, one home).
4. **One chart theme**: shared font, muted grids, restrained palette - and **one unit
   colormap shared by every figure** so unit 7 is the same color in raster, templates, and
   scatter. Titles state n ("14 units · 132 s").
5. **Tables styled**: right-aligned numerics with fixed decimals and units in the header
   (`V_pp (µV)`), sortable headers kept, sticky header row, long per-channel/per-unit
   tables behind `<details>` folds with an honest summary line.
6. **Layout**: single content column, max-width ~1100 px, generous vertical rhythm; the
   report stays fully self-contained/offline (Plotly inlined, `plotly<6` pin respected).

## §5 spikeinterface-gui (screenshot: the Qt inspector)

Upstream code - we do not restyle it, and we do not fork it for looks. Stance: it is the
expert's deep-inspection escape hatch; the workbench's own surfaces carry the curated
experience. The committed deliverable (critique #9): the caveat that currently flashes past
during `suspend()` moves into the INSPECTING panel for the Inspect action - a
correctness-relevant note shown *before* launch, per §1.7. A curated default layout is
**conditional**: D4 first verifies whether spikeinterface-gui actually supports layout
persistence (nothing in our code touches it today); if it doesn't, the caveat move is the
whole §5 deliverable. The real answer to "sigui is overwhelming" is W1's in-TUI unit
triage; W1 slice 4 inherits this spec's language.

## §6 The timeliness system (cross-cutting)

- **Report and Compare builds get progress + cancel - scoped honestly** (critique #1):
  today both run blocking, in-process, under `suspend()` with no progress channel, so
  "same modal as sorting" means building the plumbing a second time - a progress-emitting
  report path, a `report_command()` argv on the controller mirroring `sort_command()`, a
  real subprocess (cancel only works cleanly with a killable process group), and the modal
  wiring. **The report half lands with D3** (report.py is being rewritten there anyway);
  D2 gives Compare the interim honest treatment: an indeterminate modal with named step,
  ticking elapsed, and a stated no-cancel - never a silent terminal.
- **The progress protocol grows, contract-tested**: events gain **emitter-side** timing
  (critique #8) - each `phase` event carries `elapsed` seconds since run start, and a
  `phase_done` event carries the finished phase's duration, so a captured event log
  replays faithfully with no consumer-side clock skew. A terminal `result` event (units,
  noise floor, quality counts, paths) **rides alongside `done`, never replaces it** - the
  TUI synthesizes `done` from a silent rc-0 exit and its required keys are contract-pinned
  (T1). The phase list growing to five ("Save sorting") is an emitter constant; T1
  deliberately pins neither phase count nor titles. Stdout purity in `--progress json` is
  untouchable.
- **Live elapsed everywhere**: any visible run ticks; a stalled subprocess becomes visually
  distinguishable from a slow one (heartbeat gap → "no output for 90 s" amber note, not a
  frozen spinner - mountainsort4-is-slow-not-hung, LESSONS S2, gets an honest face).
- **LAST RESULT on the dashboard** (§2) is the system's memory: every action writes it.

## §7 Spec → task map (the D-track slices; graph in ROADMAP.md)

| Task | Builds | Spec | Depends on |
|---|---|---|---|
| D1 | Dashboard: panels, banner, signal budget, INSPECTING, LAST RESULT, MANAGE, help accuracy, persist active sorter + last result (new `.si_menu.json` keys, CLAUDE.md list updated same slice) | §2 | D0 veto; T1 baselines |
| D2 | Progress modals + result cards (modal-contract change named in §3), protocol extension (emitter-side timing, `result` alongside `done`), Compare interim progress, 0-unit/failure cards | §3 §6 | D0 veto; T1 protocol tests |
| D3 | Report redesign **+ the report progress plumbing** (progress-emitting report path, `report_command()`, subprocess + modal) | §4 §6 | D0 veto (M1 ✓) |
| D4 | Flow modals: sort-how-much timing, param editor pass (recommended-first ordering, overridden-vs-default marks), Manage-hub NavList consistency, sigui layout-persistence check (§5) | §3 §5 §1 | D0 veto; after D1 |

Old W0 items live here now: false-green 0-unit → D2 · INSPECTING clip → D1 · persist
active sorter → D1 · keyboard help → D1 · metric widening → M1 (unchanged, not a UI task).

## §8 Accessibility commitments

Shape-first signals and NO_COLOR safety stay law. Additions: secondary text is dim but
contrast-tested **across all accent themes on the one dark palette** (critique #7: the app
has a single dark palette with accent-color themes - a light theme would be a new palette
abstraction over all CSS and rich styles, out of the D track's scope; slice it later only
if Ben wants it); every glyph has a text neighbor (a panel legend counts, §2); focus is
always visible; keyboard model unchanged (arrows/enter/numbers/letters - no chords); all
information available at the smallest supported terminal via the yield order; report meets
sensible-contrast + keyboard-navigable TOC + alt text on every figure.
