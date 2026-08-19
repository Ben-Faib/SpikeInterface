# The workflow - from a recording to "these are the neurons"

This is the whole loop in order, in plain language: sort the recording, read what
the workbench concluded, judge the units yourself, save that judgement, take the
hard cases to Phy, bring the verdicts back, check the result against the manual
sort, and - if you ever need to - rebuild the whole thing from its own record.

Every step below gives the exact command and says where its output lands. You
only need `uv run …`; there is no environment to activate.

If you would rather press keys than type commands, most of this lives behind the
menu: `uv run python SpikeInterface_Menu.py` (on Windows, double-click
`run.bat`).

---

## The words, once

| Word | What it means here |
|---|---|
| **channel** | one wire coming off the headstage. This recording has 22; only 16 are neural, the other 6 are sync/aux inputs and are dropped before anything else happens. |
| **contact** / **site** / **electrode** | the metal pad on the probe that a channel is wired to. In this workbench the three words mean the same thing, and "ch 5" and "contact 5" name the same place. |
| **spike** | one action potential - a single brief voltage deflection, one row in the data. |
| **unit** | a *cluster* of spikes the sorter believes came from one neuron. A unit is a hypothesis about a neuron, not the neuron itself. Two units can be the same neuron split in half; one unit can be two neurons merged. |
| **peak contact** | the contact where a unit's spike is biggest. That is the workbench's answer to "where is this neuron?". |
| **sorting** | the act of grouping spikes into units. **Online** sorting happened live on the rig and lives in the `.nev`. **Offline** sorting is what we run here. **Manual/curated** sorting is a human's version. |
| **curation** | the decisions a human makes about units - this one is noise, these two are one neuron, this one should be split. |
| **strong** | this workbench's word for "passed the quality rule *on enough spikes to mean it*" (see below). A rule of thumb for orientation. It is never a claim that a unit is definitely one neuron. |
| **run** | one sort, with its own directory and its own id (`20260819-014531-7cc755`). Runs never overwrite each other; a pointer says which one is current. |

**The quality rule.** A unit is called *strong* when it passes every criterion
that could be measured on it:

```
SNR ≥ 4 · ISI ratio ≤ 0.5 · amp cutoff ≤ 0.1 · presence ≥ 0.9
```

A criterion that could not be measured is **skipped**, not failed - for example
`presence` needs 60-second bins, so it is genuinely unmeasurable on a 30-second
sort, and `amp cutoff` needs 500 spikes. A unit no criterion could be measured on
is reported as **not judged**, never as a failure. The thresholds are yours to
change: put a `quality_rule` block in `.si_menu.json` and every surface will
state the rule you actually used.

**Passing and being called strong are not the same claim.** A unit with thirty
spikes can satisfy every criterion - the ISI and amplitude criteria are counting
almost nothing at that size, and the isolation metrics cannot be computed at all.
Those units still *pass* (they are in the pass-quality count), but the surfaces
say **"passes the rule · too few spikes to judge"** rather than calling them
strong, and the headline splits the two:

```
1 strong unit (ch 7) · 5 more pass the rule on thin evidence
```

That is deliberate. A dense, well-isolated unit that missed one threshold by a
hair is a more interesting object than a four-spike unit that cleared them all,
and the headline should not say otherwise.

---

## Which surface answers which question

| You want to know | Go here | How |
|---|---|---|
| How many neurons did we find, and at which contacts? | **the report's Strong units block** | `uv run python SpikeInterface_Menu.py report` |
| Is *this particular* unit any good? | **triage** | press `u` in the menu |
| Do I need Phy? Is this unit two cells? | **the split advisory**, in the same Strong units block | `uv run python SpikeInterface_Menu.py report`, then `y` to export |
| Does our sort agree with the manual/online one? | **compare** | `uv run python scripts/compare.py --online <sorter> --nev <file>.nev` |
| What do the waveforms/correlograms actually look like? | **the Qt inspector** | press `4` in the menu |
| Which sorts do I have, and which one am I looking at? | **the run store** | `uv run python scripts/runs.py list` |
| Is my install healthy? | **the loader smoke test** | `uv run python scripts/verify_install.py` |

**About the Qt inspector (`spikeinterface-gui`).** It is upstream software we do
not control, do not restyle, and do not fork. It is the expert's deep-inspection
escape hatch - excellent for staring at waveforms, deliberately not opinionated.
The synthesis - which units look real, where they are, how they compare to the
manual sort - lives on *our* surfaces: the report block and triage. If you are
looking for a conclusion, do not go to the Qt window for it.

---

## 1. Sort the recording

```bash
uv run python scripts/run_sorting.py --duration 30    # quick check: the first 30 s
uv run python scripts/run_sorting.py                  # the real thing: all 132 s
```

Or press `2` in the menu, which runs the same thing with a live progress modal.

**Lands in:** `outputs/<sorter>/runs/<run id>/` - the saved `sorting/` and
`analyzer/`, `quality_metrics.csv`, `summary.json`, and `run_info.json` (the full
provenance: parameters, seed, package versions, git sha, probe geometry).

**Read the terminal card before moving on.** The number to check is the **noise
floor: it should be about 4 µV.** That is a property of this recording after
band-passing and referencing, so it lands in the same place for every sorter. A
value near 1 µV means the µV gain got applied twice and every amplitude on every
surface is four times too small.

Two things worth knowing:

- A `--duration` run is a **smoke** run. It never replaces a full sort as the
  current one, on purpose - a quick check should not quietly become the thing
  every surface reports.
- `tridesclous2` is **not deterministic** on this recording: identical runs have
  produced 14, 16 and 18 units. Unit ids are not stable across re-sorts. Never
  carry a unit id from one run to another by hand.

## 2. Read the strong-units block

```bash
uv run python SpikeInterface_Menu.py report      # builds and opens it
```

**Lands in:** `outputs/report.html` - one self-contained file that works offline.

The **Verdict** section opens with **Strong units**, which is the answer to "how
many neurons do we think we found, and where":

- a stamp saying which result this is (sorter, curated or raw, run id, date, and
  the window it covers) - a number you cannot trace to a run is a number you
  cannot check;
- a ranked table, strongest first: unit → contact, SNR, spikes, an isolation
  phrase in plain words, and the rule's verdict with the criterion it failed;
- one per-contact line - *"contact 2: 1 accepted · contact 7: 1 accepted + 1
  sub-threshold candidate …"*;
- the sub-threshold candidates folded below, same columns, same ranking;
- and, when a manually sorted `.nev` sits beside the recording, a column matching
  each unit against it. If that file is absent the column is absent - it is never
  guessed at.

**"Do I need Phy?" is answered in the same block.** A unit flagged *fires at
impossible intervals: likely two cells sharing this contact* is the classic
merge: its refractory violations are as dense as a second neuron firing at the
unit's own rate. The flag needs real evidence before it appears (at least 1000
spikes, an SNR the quality rule accepts, and an ISI ratio at twice the rule's own
ceiling), because that ratio divides by the spike count squared and a 30-spike
junk unit with three violations would otherwise outscore every real merge. Where
the sort saved spike amplitudes, a two-humped amplitude histogram is named as
corroboration. It is advisory: no verdict, count or threshold changes, and
nothing is blocked. The next step is `y` in the menu, which exports the sort for
Phy; the verdicts come back with `curation.py import-phy`.

The **isolation phrase** comes from the PCA metrics and says one of: *clean*,
*mostly separate*, *not clearly separate from the other units*, *overlaps another
unit on ch N*, or *too few spikes to judge*. That last one is common and honest:
below about 100 spikes those metrics cannot mean anything, so the workbench says
so rather than scoring the unit well by accident.

**Reading the manual column.** It says **"carries 100% of ch7#1"** - meaning this
unit holds every spike of that human-sorted unit. That is the direction that
answers *did we find the neuron the human found*, and it is the one to read
first. The small grey number under it is the other direction - how much of *our*
unit the human's accounts for - and it is usually small, because an offline
sorter fires five to ten times the events a careful manual selection keeps. A low
number there is not a disagreement; it is the two methods having different jobs.
When no reference unit is well recovered, the cell says *"closest: …"* and makes
no claim at all.

The dashboard says the same thing in one line, so you can see it without opening
a browser:

```
tridesclous2 · 1 strong unit of 15 · 132 s sorted
strong at ch 7 · 4 more pass the rule on thin evidence    u  triage
```

## 3. Triage the units yourself

Press `u` in the menu (or click the RESULTS section).

The list opens **strong-first** - the same ranking the report uses, because it is
the same computation - with each row naming the unit and the contact it peaks on.
The panel beside it shows the rule's verdict, the isolation phrase, the peak
contact, spike count, V_pp and every quality metric the sort wrote.

Four keys, one per unit:

| Key | Verdict | Means |
|---|---|---|
| `g` | good | a real, well-isolated single unit |
| `m` | MUA | real spikes, but more than one neuron |
| `n` | noise | not a neuron |
| `u` | unsure | looked at, undecided - come back to it |

A verdict advances the cursor, so a pass down the list is one keypress per unit.
`Esc` goes back to the dashboard.

The same verdicts can be typed instead, along with merges and splits:

```bash
uv run python scripts/curation.py label --sorter tridesclous2 --unit 15 --label noise
uv run python scripts/curation.py merge --sorter tridesclous2 --units 15,16
uv run python scripts/curation.py split --sorter tridesclous2 --unit 4
uv run python scripts/curation.py show  --sorter tridesclous2   # what has been decided
```

**Lands in:** `outputs/<sorter>/runs/<run id>/curation.json` - the record, beside
the sort it describes. Nothing is changed about the sort itself; the raw output
stays exactly as the sorter wrote it, as the audit trail.

Decisions are **recorded, not applied.** Recording a verdict does not change any
number yet - that is step 4.

## 4. Apply the decisions

```bash
uv run python scripts/curation.py apply --sorter tridesclous2
```

**Lands in:** `outputs/<sorter>/runs/<run id>/curated/` - a first-class result
with its own `sorting/`, `analyzer/`, `quality_metrics.csv` and `summary.json`,
re-scored from the curated units.

From this point on, **the curated result is what every surface shows**, and every
surface says so - the report's stamp, the dashboard's RESULTS line and the triage
header all name it as curated and say how many decisions it replays. The raw sort
stays where it was.

If you re-sort afterwards, the record stays attached to the run it curated, and
any surface reading a *different* run will tell you the curated result is over
there rather than letting it silently disappear. If the record no longer matches
the sort on disk at all, applying it is **refused** - unit ids are not stable
across re-sorts, and replaying decisions onto the wrong units would be worse than
doing nothing.

## 5. Take the hard cases to Phy

Some pairs simply do not separate in the features a scripted split can see. Phy
is the path for those.

```bash
uv run python scripts/curation.py export-phy --sorter tridesclous2
```

**Lands in:** `outputs/<sorter>/runs/<run id>/phy/` - or `curated/phy/` when a
curated result exists, since that is what the report shows too. Add `--raw` to
force the raw sort. Labels already in the record are seeded into the export, so
Phy opens showing what you have already decided instead of a blank slate.

Then, on a machine with Phy installed:

```bash
phy template-gui params.py
```

Mark clusters `good` / `mua` / `noise` (type `:quality unsure` for the
workbench's fourth verdict) and save.

## 6. Bring the verdicts back

Copy the folder back, then:

```bash
uv run python scripts/curation.py import-phy --sorter tridesclous2 --dry-run
uv run python scripts/curation.py import-phy --sorter tridesclous2
```

**Lands in:** the same `curation.json`. `--dry-run` prints what would change and
writes nothing. Re-run `apply` (step 4) afterwards to rebuild the curated result
with the new verdicts folded in.

## 7. Check it against the manual sort

```bash
uv run python scripts/compare.py --online tridesclous2 \
    --nev PFCM7_d0ephys_Block2_manuallySorted.nev --curated
```

**Lands in:** `outputs/comparison_online.html`.

Drop `--curated` to compare the raw sort. Drop `--nev` to compare against the
rig's own live online sorting instead. With no flags at all, `compare.py`
compares two offline sorters and writes `outputs/comparison.html` - a separate
file, so one page never silently replaces the other.

Read it carefully:

- The manual/online units are a **reference, not ground truth**. A low score
  means two methods disagree; it is not an error rate for either.
- A `.nev` unit number is a **per-electrode slot**, not a global identity -
  "unit 1" on electrode 5 and "unit 1" on electrode 7 are different neurons. The
  page counts electrode × slot combinations and says so.
- The coincidence window is deliberately wide (2 ms) in this mode: the `.nev`
  timestamps threshold *crossings* while an offline sorter is peak-aligned, and
  the crossings lead by about 0.6 ms here.
- The reference covers the whole recording; if your sort covers less, the
  reference is cropped to match and the page states the crop.

## 8. Rebuild a sort from its own record

Every run carries everything needed to reproduce it.

```bash
uv run python scripts/runs.py list                       # every saved run
uv run python scripts/runs.py show --sorter tridesclous2 # the current run's full record
uv run python scripts/runs.py regenerate --sorter tridesclous2
uv run python scripts/runs.py export --sorter tridesclous2 --out sort_config.json
uv run python scripts/runs.py regenerate --config sort_config.json
```

`regenerate` re-runs the sort from the record alone and prints a match report.
**Lands in:** `outputs/<sorter>/regen/<run id>/` - never in `runs/`, so a
reproducibility check can never change which run is current.

The match report compares what actually matters and states each tolerance: the
recording, the channels sorted, the preprocessing chain, the parameters, the
probe geometry, the environment, the noise floor, spike containment in both
directions, and the metric ranges. **Unit counts are reported but are not a
verdict** - this sorter is measurably non-deterministic here, so a differing
count is expected, not a failure. `sort_config.json` is small and committable:
it is how you hand a sort to someone else.

---

## When something looks wrong

| What you see | What it usually means |
|---|---|
| noise floor near **1 µV** | the µV gain was applied twice; every amplitude is ~4× too small. Do not trust any number until it reads ~4 µV again. |
| **0 units** | the detect threshold is too high. Lower `detect_threshold` in the menu's Edit parameters (`e`) and re-sort. |
| **0 strong units**, but some "pass the rule on thin evidence" | every unit that passed did so on too few spikes to mean it. Sort the full recording if you were on `--duration`; otherwise judge by hand with `u`. |
| **0 strong units** and nothing passing at all | no unit cleared the rule. Judge them by hand with `u`, or loosen `quality_rule` in `.si_menu.json` if the thresholds are wrong for this preparation - check the manual column first: a unit that carries ~100% of a human-sorted unit and misses one threshold narrowly is telling you about the threshold, not about itself. |
| every isolation phrase says **too few spikes to judge** | normal on a short `--duration` run. Sort the full recording. |
| the unit count **changed** between two identical sorts | expected - `tridesclous2` is non-deterministic on this recording. Compare spikes, not unit counts. |
| a metric reads **–** | it could not be computed for that unit, which is not the same as zero. The surfaces never print a number they do not have. |
