# DESIGN_UX.md — the workbench design spec (D0)

*Drafted 2026-08-18 from Ben's overhaul directive and screenshots of every surface (dashboard,
sort-progress modal, sort-how-much modal, the HTML report, spikeinterface-gui). **Ben veto
gate: nothing in D1–D4 is built until Ben approves or amends this spec.** Section §7 maps
spec → implementation tasks. The peer session's feasibility critique
(`docs/design/DESIGN_CRITIQUE_2026-08-18.md`, 10 findings) was folded in the same day —
the spec below is the post-critique version, ready for the veto. **§2 was rewritten
2026-08-19 to describe the F2 dashboard as built** — it is the spec of record for the
dashboard, and it says which of §1's principles that design keeps and which it drops.*

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
   accent — the thing to look at or do next), normal, secondary (dim — provenance, hints).
   Anything that would be a fourth tier gets cut or moved behind the cursor/a fold.
4. **Ample room.** Panels get inner padding (1 cell TUI / generous rem in HTML); one blank
   line between groups; no full-width separator rules where a gap does the job. When space
   runs out, chrome yields before content (the existing responsive-yield order stays law,
   as do the never-clip Pilot tests).
5. **Color is a role, never decoration, never the only carrier** (NO_COLOR/mono safety is
   existing culture — keep it). Roles: **accent** = focus & the primary action; **green** =
   verified/passed only; **amber** = needs attention, has a next step; **red** = failure,
   has a log; **dim** = secondary. A green that doesn't mean "verified" is a defect.
6. **Timeliness doctrine.** Anything that takes over ~1 s shows what it is doing (named
   phase), that it is alive (elapsed ticking, spinner/heartbeat), and honest progress
   (determinate bar only when the underlying step reports real fractions — a bar at 100%
   under a still-running step, as the current sort modal shows, is a lie by layout). And
   every run **ends with its result presented**, not a vanishing footer line.
7. **Every dead-end names its next step.** Empty, zero, and error states say what happened
   and the one action that helps ("0 units — lower detect_threshold in Edit parameters").

## §2 The dashboard (F2, the researcher dashboard — current spec of record)

*History: D1 built a three-panel spec; D5 (Ben, actions-first) put the sorter list behind
the `t` picker and made six numbered actions the screen; D6 replaced boxed panels with a
whitespace + hairline language. **F2 (Ben's directive of record, 2026-08-19 ~03:00) is what
this section now describes** — the D6 dashboard was judged not sufficient: it showed six of
the workbench's fourteen functions and hid the rest behind bare letters on one dim footer
line, which is unreadable to a researcher meeting the app cold. This section was rewritten
to match what was built, not the other way round. What §1 still binds, and what F2 dropped,
is stated at the end.*

```
                          █ SPIKE █             (crest: TALL terminals only, ≥34 rows)
   ───────────── University of Pittsburgh · SpikeInterface ─────────────

   DATA  ✓ all 3 streams      PROBE  NeuroNexus A1x16-3mm-100-703 · 16 ch @ 100 µm ✓
   SORT  ★ tridesclous2 · 15 units · 132 s saved · Ready to run    t  change

   RESULTS ────────────────────────────────────────────────────────────
   tridesclous2 · 1 strong unit of 15 · 132 s sorted
   strong at ch 7 · 4 more pass the rule on thin evidence    u  triage
   V_pp 33.4 µV · SNR 5.3 · noise 3.98 µV · yield 88%

   GET DATA ───────────────────────────────────────────────────────────
    d   Data files            which files loaded, and where    f  folder
    p   Probe geometry        the electrode map every sort uses
    1   Explore the recording static figures — LFP, events, rates
    6   Watch the traces      scroll the raw signal in a window
    v   Check the install     every library and loader, pass or fail

   SORT & CURATE ──────────────────────────────────────────────────────
    t   Choose the sorter     which algorithm finds the units
    e   Sorter settings       the parameters the next sort uses
    2   Sort the recording    finds units in the broadband signal
    u   Judge the units       good / MUA / noise, one key per unit
    y   Export to Phy         a folder to curate the hard cases

   LOOK & SHARE ───────────────────────────────────────────────────────
    3   Build the report      one HTML page: units, quality, provenance
    4   Inspect in the GUI    waveforms + correlograms in a window
    5   Compare two sorts     how much two saved sorts agree
    r   Reopen last result    the page you built most recently

   LAST  ✓ report · 14:18 → outputs/report.html   r reopen
   ↑/↓ move · ↵ run · or press the key shown on the row · m sorters & Docker · c colour · ? help · q quit
```

**Three zones, one job each.** *State* (DATA/PROBE · SORT · RESULTS) says where you are.
*The workflow list* says what you can do. *Memory* (LAST + the key line) says what you last
did and what is left over. A fact lives in exactly one zone: the banner never repeats a
result, the rows never repeat state, RESULTS never repeats the banner.

- **Every function is a visible, labelled row carrying its own key.** All fourteen:
  five in GET DATA, five in SORT & CURATE, four in LOOK & SHARE. Nothing lives only
  behind a letter on the footer. The hint says what the row **produces**, not how it
  works. Only housekeeping with no workflow meaning stays on the key line — `m`
  manage sorters/Docker, `c` colour, `? `help, `q` quit — plus `x` (manage the active
  sorter) and `w` (re-open a running download), which are documented in Help.
- **Stages are the navigation.** The three headings are the D6 hairline language
  (dim label + rule) rendered as non-selectable rows inside the same list, so ↑/↓
  steps over them and the grouping cannot drift out of sync with the rows.
- **Keys were not remapped.** 1-6 keep the meanings they have always had; the redesign
  moved the rows, not the keys. Every existing binding, `docs/WORKFLOW.md`, and every
  in-app hint that names a key stays true. A key press also moves the cursor to its
  row, so pressing a key and pressing Enter on the row are one gesture.
- **"Data files/folder" is one row with two doors**: `d` says what loaded, and a
  second ` f ` chip on the same row points the workbench at another folder.
- **RESULTS moved above the list** and keeps face1's takeaway verbatim — the rollup
  headline, the site line, and the pressable ` u  triage` chip (click anywhere on
  RESULTS for the mouse path). The rollup's wording belongs to `sort_summary`.
- **No boxes, and no prose.** Sections are a dim label + hairline rule over
  borderless content, separated by blank-line air; the rules all end in the same
  column. D6's context *sentence* (the active sorter's description) was **cut** —
  it was the one paragraph on the screen, and the picker already shows a
  description exactly where you are choosing a sorter.
- **Hints are dropped whole, never ellipsised.** Below about 72 columns a hint that
  cannot fit is removed and the row is its title alone; half a sentence is noise.
- **Crest is a tall-terminal luxury** (≥34 rows); at 80×24 it is simply absent.

**The yield ladder** (`menu_app.SpikeMenuApp._LADDER`, walked by `_plan`) is a budget, not
a set of tiers: the layout walks the ladder and stops the moment the screen fits, so nothing
yields that did not have to.

| # | Yields | Rows |
|---|---|---|
| 1 | the blank line above each stage group | 2 |
| 2 | the blank lines between the screen's blocks | 3 |
| 3 | the centred title rule | 1 |
| 4 | RESULTS' label rule + metrics line (the takeaway stays) | 2 |
| 5 | the LAST RESULT line | 1 |
| 6 | RESULTS entirely | 2 |
| 7 | the DATA / SORT state rows | 2 |
| 8 | the three stage headings | 3 |

The fourteen rows never yield; below the bottom of the ladder the list scrolls, so every
function stays reachable. **At 80×24 the ladder stops at step 4**: the whole workflow, both
state rows, the takeaway and the LAST line are on screen at once and nothing scrolls. The
budget counts the rows its own painters produce (`_results_lines`, `_list_rows`), so it
cannot drift from what is painted — the D6 review-F6 failure closed by construction. Pinned
by `test_painted_rows_match_the_budget`, `test_default_terminal_shows_the_whole_workflow`,
`test_the_ladder_yields_air_then_chrome_then_state` and the SVG snapshots.

**Help** (`ui.HELP_TOPICS`, one source for the Textual and typed-fallback screens) is
rebuilt as *which question → which surface → which key*, in the same plain words as
`docs/WORKFLOW.md` — which is the canonical version; the two must not diverge into a third
vocabulary. Topics: Start here · Where do I look? · the three stages · The words · If it
looks wrong · Sorters & Docker · Probe geometry · Data files · Keyboard · About. The body is
a laid-out pane 50 columns wide at the default terminal, so its lines are written to that
width and pinned there.

**What F2 kept from §1**: one fact one place (§1.1 — the three zones are the mechanism);
signal budget (§1.2 — a row is a key chip, a title and one dim phrase); hierarchy by weight
(§1.3); air yields before content (§1.4); colour as a role, never the only carrier (§1.5);
every dead end names its next step (§1.7 — a needs-data row says "needs the recording
files" in place of its hint). **What F2 dropped**: the context sentence under SORT, and
§1.4's "ample room" read as inner padding — the room here is between groups, not inside
boxes. The `t` picker, RESULTS gating (a saved sort must exist), and LAST RESULT semantics
are unchanged.

## §3 The sort experience (screenshots: SORTING modal ×2, "Sort how much?")

**Findings.** The phase checklist is the right idea, wrongly finished: it shows only
Read/Preprocess/Sort (save, analyze, metrics — half the pipeline — happen invisibly);
raw sorter internals leak as truncated jargon (`split_clusters with local_feature…`); a
bar reads "100%" while work continues; no elapsed time anywhere; and completion dismisses
to a one-line footer message instead of presenting the result.

**Redesign — the modal is the run's honest narrator, then its results card.**

```
  SORTING tridesclous2 · full recording · elapsed 2:14

   ✓ Read broadband        3.2 s
   ✓ Preprocess            4.1 s
   ▶ Sort                  1:58    clustering peaks (29,355 kept)
   · Save sorting
   · Analyze + metrics

   phase 3 of 5  ▂▂▂▂▂▂▂▂░░░░░░  (bar only when the step reports real progress;
                                   otherwise the spinner + ticking elapsed carry aliveness)
   Esc cancel — kills the whole worker tree
```

On completion the same modal becomes the **result card** (no green-and-gone):

```
  ✓ SORTED · tridesclous2 · full recording · 4:07

    14 units found        noise floor 4.0 µV ✓
    9 pass quality thresholds (once M1 lands; until then: units + canary)
    saved → outputs/tridesclous2/

    ↵ close · 3 build report · 4 inspect in GUI
```

- **0 units is an amber card** with the detect_threshold hint — the false-green dead-end
  dies at the source. **Failure is a red card** with the last stderr lines inline and the
  log path (the log already exists on disk; surface it).
- **Result-card actions are a modal-contract change, named as such** (critique #2): the
  dismissal shape grows an optional `next_action` the app dispatches after the pop —
  report via `DISPATCH`, inspect via the `_self` fresh-process path — and the Pilot tests
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

**Redesign — verdict first, evidence below, one visual system.**

1. **Verdict header**: recording · sorter · date, then four stat tiles — **units**,
   **pass-quality count** (M1's widened metrics are live; the threshold *rule* stays W1's),
   **noise floor**, **window sorted** (with the partial-sort caveat inline when eff <
   total). **The noise-floor tile makes no pass/fail claim** (critique #4): the ~4 µV
   canary is an observed regression signal, not a validated threshold — the tile shows the
   number with its expected band as text ("4.0 µV · expected ≈3.9–4.1 for this rig,
   post-bandpass+CMR"), and only an *outside-band* value turns the tile amber with the
   double-scaling explanation. Never a green ✓ science claim.
2. **Sticky table of contents** (left rail ≥1100 px, collapsing to a top bar below) with
   per-section status glyphs — the current status table becomes navigation.
3. **Sections re-cut in reader order**: 1 Verdict · 2 Sorted units (raster, rates,
   templates) · 3 Quality metrics (table + scatter) · 4 Array & yield · 5 Probe &
   channels · 6 Recording context (LFP, online .nev units, events — demoted: it's input
   context, not results) · 7 Provenance (status table + About merged, one home).
4. **One chart theme**: shared font, muted grids, restrained palette — and **one unit
   colormap shared by every figure** so unit 7 is the same color in raster, templates, and
   scatter. Titles state n ("14 units · 132 s").
5. **Tables styled**: right-aligned numerics with fixed decimals and units in the header
   (`V_pp (µV)`), sortable headers kept, sticky header row, long per-channel/per-unit
   tables behind `<details>` folds with an honest summary line.
6. **Layout**: single content column, max-width ~1100 px, generous vertical rhythm; the
   report stays fully self-contained/offline (Plotly inlined, `plotly<6` pin respected).

## §5 spikeinterface-gui (screenshot: the Qt inspector)

Upstream code — we do not restyle it, and we do not fork it for looks. Stance: it is the
expert's deep-inspection escape hatch; the workbench's own surfaces carry the curated
experience. The committed deliverable (critique #9): the caveat that currently flashes past
during `suspend()` moves into the INSPECTING panel for the Inspect action — a
correctness-relevant note shown *before* launch, per §1.7. A curated default layout is
**conditional**: D4 first verifies whether spikeinterface-gui actually supports layout
persistence (nothing in our code touches it today); if it doesn't, the caveat move is the
whole §5 deliverable. The real answer to "sigui is overwhelming" is W1's in-TUI unit
triage; W1 slice 4 inherits this spec's language.

## §6 The timeliness system (cross-cutting)

- **Report and Compare builds get progress + cancel — scoped honestly** (critique #1):
  today both run blocking, in-process, under `suspend()` with no progress channel, so
  "same modal as sorting" means building the plumbing a second time — a progress-emitting
  report path, a `report_command()` argv on the controller mirroring `sort_command()`, a
  real subprocess (cancel only works cleanly with a killable process group), and the modal
  wiring. **The report half lands with D3** (report.py is being rewritten there anyway);
  D2 gives Compare the interim honest treatment: an indeterminate modal with named step,
  ticking elapsed, and a stated no-cancel — never a silent terminal.
- **The progress protocol grows, contract-tested**: events gain **emitter-side** timing
  (critique #8) — each `phase` event carries `elapsed` seconds since run start, and a
  `phase_done` event carries the finished phase's duration, so a captured event log
  replays faithfully with no consumer-side clock skew. A terminal `result` event (units,
  noise floor, quality counts, paths) **rides alongside `done`, never replaces it** — the
  TUI synthesizes `done` from a silent rc-0 exit and its required keys are contract-pinned
  (T1). The phase list growing to five ("Save sorting") is an emitter constant; T1
  deliberately pins neither phase count nor titles. Stdout purity in `--progress json` is
  untouchable.
- **Live elapsed everywhere**: any visible run ticks; a stalled subprocess becomes visually
  distinguishable from a slow one (heartbeat gap → "no output for 90 s" amber note, not a
  frozen spinner — mountainsort4-is-slow-not-hung, LESSONS S2, gets an honest face).
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
has a single dark palette with accent-color themes — a light theme would be a new palette
abstraction over all CSS and rich styles, out of the D track's scope; slice it later only
if Ben wants it); every glyph has a text neighbor (a panel legend counts, §2); focus is
always visible; keyboard model unchanged (arrows/enter/numbers/letters — no chords); all
information available at the smallest supported terminal via the yield order; report meets
sensible-contrast + keyboard-navigable TOC + alt text on every figure.
