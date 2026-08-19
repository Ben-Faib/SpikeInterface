# GOAL PRESENT: the lab-meeting arc (diagnosis, sweep, facelift, deck)

*Written 2026-08-19 from Ben's interview (decisions of record below). This brief is the
detail layer for THE CONDUCTOR v4 prompt in ROADMAP.md. Read order for the running
session: ROADMAP NOW box -> the v4 prompt -> this brief -> the module docstrings it
names. SEALS.md carries where things stand; CLAUDE.md's invariants bind every edit.*

## Intent

Ben presents the workbench at Tracy's lab meeting (next week or later, no fixed date:
features first, deck assembled last from finished pieces). The talk is ~10 minutes,
8-12 slides, real .pptx, light on text, heavy on visuals, with a live TUI demo in the
middle and screenshot backups in an appendix. The story: manual spike sorting is slow
and subjective; SpikeInterface rescues; here is how the workbench judges units and
stays honest; live demo; here is the honest verdict on our own recording and the
routes to untangle its one real catch (the merges).

## Ben's decisions of record (2026-08-19 interview)

1. **Split path chosen for the merges**: keep the default quality rule unchanged.
   The workbench gains a merge-diagnosis advisory (below) and a ready-to-open Phy
   export; Ben does the actual splits in Phy later ("prep only"). He will NOT have
   split before the presentation, so the deck shows the current state honestly plus
   the escape routes.
2. **Stray run deleted**: `outputs/tridesclous2/runs/20260819-022232-4e9932` (his
   call: "delete it").
3. **P3 is a standing assumption now, not a wait**: no adapter map is coming;
   channel->site identity wiring is the accepted assumption. W3 (fuller face) and
   W4 (lab recordings) stay recorded as gated.
4. **NO EM DASHES, anywhere, ever** (hard boundary): the character U+2014 disappears
   from the whole repo: UI strings, HTML surfaces, docs, code comments, docstrings,
   board files, commit messages, the deck. Purge existing occurrences and pin with a
   repo-wide test so it cannot return. (Snapshot SVGs that merely mirror purged UI
   strings get re-baselined deliberately, per tests/README.md.)
5. **Palette anchor is periwinkle** across ALL surfaces: report, comparison pages,
   the new sweep page, and the deck share one validated chart palette (see Viz
   unification below).
6. **Deck**: periwinkle-washed background with darker periwinkle accents; NO credits
   anywhere; real PFCM7-derived figures used freely (raw data still never leaves the
   machine; derived charts and screenshots are fine); intuition diagrams on slides
   with a per-slide speaker SCRIPT in the pptx notes carrying the actual numbers and
   thresholds; live demo break with a backup-screenshot appendix; the sorter
   shootout is a real slide with real numbers, whatever they say.

## Work items (dependency order; features first, deck last)

### 1. Em-dash purge + housekeeping (first, so everything after complies)

Repo-wide U+2014 removal with sensible substitutions (hyphen, colon, period, middot;
rewrite sentences where punctuation swaps read badly). Add a test that greps the repo
(source, docs, scripts, tests, board files) and fails on any U+2014; exempt nothing.
Delete the stray run dir (decision 2). Board rewording for P3 (decision 3).

### 2. Merge diagnosis: "when do I need to split?" (sort_summary owns it)

A per-unit advisory that works on NOVEL data (no reference .nev needed), simple and
plain-worded, quoted by report, triage, and dashboard from ONE home (the rollup),
never a certification and never blocking:

- Evidence available without a reference: a unit with a substantial spike count and
  solid SNR whose ISI violations ratio sits far above threshold is firing at
  impossible intervals: the classic two-cells-one-cluster signature. Where the
  analyzer carries spike_amplitudes, amplitude bimodality is a second signal.
- Plain words on the surface, e.g.: "fires at impossible intervals: likely two cells
  sharing this contact. Consider splitting (y exports to Phy)".
- Exact criteria and wording are the builder's design, taken through the slice's
  Fable review. The known truths that calibrate it: on this recording the four
  dense merged units run ISI 1.06-1.36 with thousands of spikes; the thin junk
  units cannot fire it (evidence floor); WORKFLOW.md's "which surface answers which
  question" table gains the "do I need Phy?" row.

### 3. Parameter integrity (Ben: "make sure parameter editing works as intended")

Verify the full round trip with a test: param editor edits -> `.si_menu.json`
`sorter_params` -> `run_sorting` effective params -> `run_info.json` provenance.
Defaults shown must match what actually runs. The sweep page (item 4) states the
current parameters explicitly.

### 4. The sorter sweep (the shootout)

Full-recording sorts, through the store (never clobber), one per sorter:
`spykingcircus2`, `lupin`, `simple` (local) + `mountainsort5`, `waveclus` (Docker;
LESSONS S2: version skew can fake failure, slow is not hung). No GPU sorters here;
Kilosort4 belongs on the deck slide as the lab-box option.

Judge every sorter against the manual .nev with the existing matcher (one home,
compare.match_manual): per manual unit, recovery; and the PAIR TEST per electrode
that carries two manual units: split success means two DISTINCT sorter units each
recovering one slot-unit at >= 0.8, with their ISI ratios reported. tdc2's known
result is the baseline row. Honest failures (a sorter that crashes or finds nothing)
are rows too, stated plainly.

### 5. The sweep-results page (new HTML surface)

One self-contained HTML page (same discipline as report.py: inlined, offline):
every swept sorter, recovery per manual unit, pair-split verdicts, unit counts,
noise floor (the ~4 uV canary is a cross-sorter verdict), runtime, and the current
sorter parameters stated. Built on the unified palette. This is deck source
material: its key visual becomes the shootout slide.

### 6. report.html facelift + content audit

A pass over the existing report for missing key evidence, with the merge story in
mind: per-unit ISI histograms (the diagnosis's own evidence), amplitude
distributions, waveform overlays are the candidates; the audit decides what earns a
place. Apply the unified palette. No layout rewrite for its own sake: content
completeness first, coherence second.

### 7. Viz unification (the /dataviz method; load that skill before building)

Build the periwinkle-anchored palette properly: categorical order, sequential ramp,
diverging pair, status colors, light AND dark variants, validated with the skill's
`validate_palette.js` (never eyeballed). Apply across report.html, comparison pages,
and the sweep page so every chart reads as one system; the deck consumes the same
palette. The palette definition lives in ONE place the surfaces read (a small module
or constants file with the validation command documented beside it).

### 8. The deck (last, from finished pieces)

Real .pptx (the pptx skill), 8-12 slides, 16:9, periwinkle-washed, no credits, no em
dashes, light on text. Every slide gets speaker notes: bullet points of what to say,
with the numbers and thresholds living in the notes, not on the slide. Draft arc
(builder may refine; the story beats are fixed):

1. Title.
2. The problem: manual sorting is hours per recording, subjective, hard to audit.
3. SpikeInterface to the rescue: one standard, many sorters, reproducible.
4. What the workbench does: get data -> sort & curate -> look & share (mirrors the
   dashboard's three stages).
5. How a unit is judged, intuition 1: SNR (waveform vs the ~4 uV noise floor).
6. Intuition 2: ISI and the refractory period (a neuron cannot double-tap; impossible
   intervals mean two cells are wearing one label).
7. Honesty gates: too-few-spikes floor, NaN never masquerades as a verdict.
8. DEMO break (live TUI: sort -> triage -> report).
9. The verdict on our recording: 97-100% of hand-sorted neurons found; the honest
   catch: merges, flagged by ISI exactly as designed.
10. Untangling routes: the sorter shootout (real sweep numbers) + Phy splitting +
    GPU sorters (Kilosort4) on the lab's Windows box.
11. Close: what this buys the lab.
Appendix: backup screenshots (dashboard, triage, report, sweep page) for demo
failure, plus any overflow charts.

Charts on slides are pre-rendered images from the unified palette. Numbers quoted in
the script come from the actual finished pieces (sweep page, report), never invented.

## Boundaries

- CLAUDE.md invariants bind everything (uV double-scaling gate, ~4 uV canary, aux +
  bad channels drop before CMR, stdout purity, view imports no SI, runs never
  clobber, explicit-path commits).
- No GPU sorters locally; Docker is the fallback for sorters not installed.
- Raw data never enters git or leaves the machine; the deck ships derived figures
  and screenshots only.
- The quality rule's defaults do not change (decision 1). The diagnosis is advisory.
- Builders on Opus, reviews on Fable, one fresh-context review per substantive
  slice; deliberate snapshot re-baselines only.
- The deck and sweep page contain real numbers from real runs; if the sweep finds no
  splitter, the shootout slide says so and the Phy + GPU routes carry the story.
