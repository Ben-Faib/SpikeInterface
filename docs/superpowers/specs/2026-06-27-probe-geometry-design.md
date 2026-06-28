# Probe geometry layer — design

- **Date:** 2026-06-27
- **Status:** approved (design); pending implementation plan
- **Topic:** add an editable probe-geometry layer to the SpikeInterface menu workspace, surface it in the UI, feed it into the pipeline, and use it to suggest applicable sorters.

## Motivation

The Blackrock/Ripple files in this workspace carry **no electrode geometry**
(`get_probe()` raises; there are no channel locations). Today every sortable
recording gets a hard-coded placeholder "independent-channel" probe
(`attach_dummy_probe()` — one column, 250 µm pitch, so no two channels are
neighbours). That keeps per-unit results valid but makes all cross-channel
*spatial* information non-physical, and it means the sorter recommendation can't
account for geometry — yet **geometry is exactly what decides which sorters are
appropriate** (a dense 2-D array wants kilosort/herdingspikes; independent
channels want waveclus/tridesclous2).

This feature adds a first-class, user-editable **probe layer**: choose/define a
probe geometry (library-based, since geometry varies per recording), switch
profiles in the UI, edit/add/remove them, feed the chosen geometry through the
sort/report/GUI pipeline, and let the geometry **softly re-rank and explain**
which sorters fit.

## Decisions (settled in brainstorming)

1. **Library-based**, not a single hard-coded real probe — geometry varies per
   recording. Built-in standard presets + user-editable profiles; the current
   placeholder becomes one explicit, labelled choice (`independent`).
   **Update (user-confirmed):** this recording's real probe is a **NeuroNexus
   A1x16-3mm-100-703** (16 sites, single shank, 100 µm pitch). It is verified to
   match the data (channels `raw 1`–`raw 16`; `analog 1`–`analog 6` are aux,
   dropped before sorting → 16 neural channels), so it ships as a built-in and is
   the **default active probe** (`nnx-a1x16-3mm-100`), not `independent`.
2. **Hybrid geometry input:** (a) parametric generators (linear, 2-D grid,
   tetrode, independent), (b) the `probeinterface` real-probe catalog
   (manufacturer + model), (c) import a `probeinterface` JSON file. No raw
   per-contact x,y typing in the terminal.
3. **Soft re-rank + explain** for sorter suggestions: geometry computes a per
   -sorter fit score; good-fit sorters get a badge and float up; the ★ default
   becomes the top fit for the active probe; **nothing is blocked**; the
   INSPECTING panel explains why a sorter fits or doesn't.
4. **Optional first-run step after Welcome**, gated by a new `seen_probe_setup`
   flag, with an explicit "Skip — use placeholder for now" escape.

## Goals

- A probe-geometry layer that is the single source of truth for "what does the
  electrode array look like," shaped exactly like the existing `sorters.py`
  registry (plain-data API, lazy heavy imports, no SpikeInterface in the TUI).
- Switch / add / edit / remove probe profiles entirely in the UI (and at parity
  in the non-Textual fallback menu).
- The chosen geometry flows into sorting, the HTML report, and the Qt GUI/trace
  views; the placeholder-geometry caveat becomes **conditional**.
- Geometry-driven sorter suggestions (soft re-rank + badges + explanations).
- A one-time, skippable first-run probe-setup prompt.

## Non-goals (YAGNI)

- No raw per-contact x,y coordinate typing in the TUI (use generators / catalog
  / file import instead).
- No in-terminal probe *plot* / drawing — a text summary only. The existing Qt
  `gui`/`traces` views already render real geometry once a probe is attached.
- No auto-detection of geometry from the Blackrock headers — they carry none;
  that is the entire premise.
- No multiple-probes-per-recording (multi-probe `ProbeGroup`) in v1.
- No change to how the raw data is loaded/streamed — only which probe is attached.

---

## Section 1 — Data model & new module

### New module: `scripts/probes.py`

The single source of truth for probe geometry, mirroring `scripts/sorters.py`:
imports `probeinterface` (and, only inside the build path, nothing from
SpikeInterface beyond what `set_probe` needs) **lazily** so importing the module
stays cheap; every public function returns plain Python data (dicts / lists /
str) so the Textual app can stay free of `probeinterface`/SpikeInterface imports.

### Probe profile schema

One dict per profile:

```jsonc
{
  "name": "linear-16-50um",          // unique kebab-case key (identity)
  "label": "Linear · 16 ch @ 50 µm", // display string
  "kind": "independent|linear|grid|tetrode|library|file",
  "params": { ... },                 // kind-specific (see below)
  "builtin": false,                  // built-ins ship in code; copy-to-edit; never deleted
  "note": ""                         // optional one-line description
}
```

Kind-specific `params`:

| kind | params |
|---|---|
| `independent` | `{ "pitch_um": 250.0 }` — the placeholder; **auto-sizes** to the recording's neural-channel count |
| `linear` | `{ "n": 16, "pitch_um": 50.0 }` — single column |
| `grid` | `{ "rows": 8, "cols": 4, "xpitch_um": 50.0, "ypitch_um": 50.0 }` |
| `tetrode` | `{ "n_tetrodes": 4, "within_um": 25.0, "between_um": 300.0 }` |
| `library` | `{ "manufacturer": "neuronexus", "model": "A1x16-..." }` — resolved via `probeinterface.get_probe` |
| `file` | `{ "path": "/abs/or/repo-relative/probe.json" }` — a `probeinterface` JSON |

### Persistence

- **Built-in presets** live in code (`probes.py: BUILTINS`) and cannot be deleted
  — only duplicated to a new editable profile.
- **User-created / edited profiles** persist to a new git-ignored **`probes.json`**
  at repo root (same pattern/`.gitignore` treatment as `.si_menu.json`). Shape:
  `{ "profiles": [ <profile>, ... ] }`.
- The **active profile name** persists as a new `active_probe` key in
  `.si_menu.json` (alongside `theme`/`use_docker`/`sorter_params`/`seen_welcome`),
  plus a new `seen_probe_setup` first-run flag. Default active =
  `nnx-a1x16-3mm-100` (this recording's real probe); `independent` remains a
  selectable profile for recordings whose geometry is unknown.

`.gitignore` adds `probes.json`.

### Channel-count rule

- `independent` always **auto-sizes** to the recording's neural-channel count, so
  it can never mismatch (matches `attach_dummy_probe` today).
- Every other profile has a fixed contact count. The manager shows the loaded
  recording's neural-channel count and **flags** any profile whose count differs
  (still selectable, but flagged). **Applying** a mismatched fixed-count probe is
  refused with a clear message — never a silent mis-map.
- Device-channel mapping defaults to **identity order** (contact *i* ↔ channel
  *i*), exactly as `attach_dummy_probe` does today
  (`set_device_channel_indices(np.arange(n))`). `library`/`file` profiles may
  carry their own mapping if the source defines one.

---

## Section 2 — Construction & pipeline integration

### `probes.py` public API (plain data)

```python
library() -> list[dict]                  # built-in + user profiles, ordered
active() -> dict                         # the active profile (default: independent)
set_active(name) -> None                 # persist active_probe in .si_menu.json
get(name) -> dict | None
save_profile(profile) -> None            # upsert a user profile in probes.json
delete_profile(name) -> tuple[bool,str]  # user profiles only; never built-ins
duplicate(name, new_name, new_label) -> dict

# probeinterface catalog (lazy)
catalog_manufacturers() -> list[str]
catalog_models(manufacturer) -> list[str]

# geometry introspection (no SI)
summary(profile) -> str                  # "16 contacts · linear · 50 µm pitch · 750 µm span"
geometry_features(profile) -> dict       # {n, layout, min_pitch_um, density_class}
contact_count(profile) -> int | None     # None = auto-size (independent)

# construction (attaches to a recording)
build(profile, n_channels) -> "probeinterface.Probe"   # raises on count mismatch
```

`build()` dispatches on `kind`: `independent`→`generate_linear_probe`
(re-using/replacing `attach_dummy_probe`'s logic), `linear`→`generate_linear_probe`,
`grid`→`generate_multi_columns_probe` (or a grid helper), `tetrode`→tetrode
generator, `library`→`get_probe(manufacturer, model)`, `file`→`read_probeinterface`.
It always sets device-channel indices and validates the contact count against
`n_channels`.

### `blackrock_io` changes

- Keep `attach_dummy_probe` as the `independent` build path: `probes.build` calls
  it for `kind == "independent"`, so there is one code path for the placeholder.
- Callers apply a real probe with `probes.build(profile, n) + recording.set_probe(...)`
  **after** any channel selection, so the contact count matches the kept neural
  channels. (No new `blackrock_io` helper is needed — `probes.build` + `set_probe`
  is the seam.)

### `run_sorting.py` changes

- New CLI: `--probe <name>` (look up in the library) and `--probe-file <path>`
  (a `probeinterface` JSON, equivalent to a `file` profile). Default: the active
  profile from config (the NNX A1x16, which matches the 16 kept neural channels),
  falling back to `independent` if unset.
- Pipeline order becomes: `read_broadband(attach_probe=False)` → drop analog aux
  channels (`neural_channel_ids`/`select_channels`) → **apply the resolved probe**
  (`probes.build(profile, n_kept)` + `set_probe`) → bandpass → common reference →
  sort. (Today's two `attach_dummy_probe` calls collapse into one
  apply-after-drop step.)
- Clear error if a fixed-count probe doesn't match the kept channel count.

### Controller / menu

- `MenuController.sort_command(span)` appends `--probe <active_probe>` so in-UI
  sorts use the chosen geometry.
- `report.build_report(...)` and the `gui`/`traces` launchers load the recording
  with the active probe (so spatial views and unit-location plots are real).
- `_GEOMETRY_CAVEAT` (launcher) and the report's "placeholder independent-channel
  probe" / geometry notices become **conditional**: shown only while
  `independent` is active; otherwise replaced by "geometry: <profile label>".

---

## Section 3 — Sorter recommendation engine

A geometry → sorter-fit scorer living in `probes.py` (keeps all geometry logic in
one module; the controller imports it and exposes `sorter_fit(...)` to the view).

### Inputs (from `geometry_features`)

- `n` — contact count.
- `layout` ∈ `independent | linear | grid2d | multishank`.
- `min_pitch_um` — smallest centre-to-centre contact distance (independent ⇒ ∞).
- `density_class` ∈ `independent | sparse | dense`, computed from `min_pitch_um`
  with tunable constants (`DENSE_MAX_UM = 60`, `INDEP_MIN_UM = 150`):
  - **`dense`** — `min_pitch_um ≤ 60` (strong waveform sharing; Neuropixels ~20 µm,
    NeuroNexus poly2/3 ~50 µm).
  - **`sparse`** — `60 < min_pitch_um < 150` (some sharing; e.g. NeuroNexus
    single-shank @ 100 µm).
  - **`independent`** — `kind == independent`, **or** `min_pitch_um ≥ 150` (no
    physical waveform sharing — a contact's spike isn't seen on its neighbour).
    This is why a 400 µm Utah array and a 300 µm flexible shank are treated as
    *electrically independent*, matching the spike-sorting literature.

### Suitability table

A curated table (like `sorters.DESCRIPTIONS`) marking each sorter good/ok/poor per
geometry class with a one-line reason. Grounded in the research brief
(see Appendix §4 sources — Kilosort needs ≤~40 µm pitch; HerdingSpikes is "poor"
above 60 µm; MountainSort4 is best at low channel counts; WaveClus/Combinato are
single-channel/tetrode tools):

| sorter | independent | sparse | dense | note |
|---|---|---|---|---|
| tridesclous2 | **good** | **good** | ok | solid general default; tetrode→Neuropixels |
| mountainsort4 | **good** | good | ok | best at low channel counts / tetrodes |
| mountainsort5 | ok | good | **good** | density clustering; scales to many channels |
| spykingcircus2 | ok | good | **good** | template matching; strong on dense |
| waveclus | **good** | ok | poor | single-channel / tetrode / few channels |
| combinato | **good** | ok | poor | single-unit / long recordings |
| tridesclous (v1) | good | ok | ok | tetrode-oriented legacy |
| spykingcircus (v1) | ok | ok | ok | legacy template matching |
| herdingspikes | **poor** | **poor** | **good** | needs dense neighbours; poor above ~60 µm |
| ironclust | **poor** | ok | **good** | high-density / drift |
| kilosort4 / 3 / 2_5 / 2 | poor | poor | **good** | needs ≤~40 µm pitch; GPU-gated here (fit still shown) |
| pykilosort / yass | poor | poor | **good** | dense; GPU-gated here |
| simple / lupin | ok | ok | ok | smoke-test / basic |

The geometry-aware ★ default resolves to the top **runnable** good-fit: this keeps
`tridesclous2` for `independent` (today's default) and floats `spykingcircus2` /
`mountainsort5` up for a dense probe (GPU-gated kilosort shows a "good fit" badge
but stays unselectable, exactly as today).

### API & effect

```python
fit(name, profile) -> {"rank": "good|ok|poor", "reason": "..."}
ranked(profiles_or_features, names) -> list[(name, rank, reason)]
```

Soft, non-destructive effect in the UI:

- The sorter list **re-ranks within each existing group** (`ready` / `docker` /
  `gpu` / `unavailable` stay; order *inside* a group floats good-fit up).
- Good-fit rows show a "✓ fits this probe" badge; poor-fit a "△ weak for this
  probe".
- The ★ **recommended default becomes the top fit** for the active probe (falls
  back to `tridesclous2` for `independent`, preserving today's default).
- The INSPECTING sorter explanation gains a "**Fit for <probe>:** <reason>" line.
- The SORT banner's readiness/`★` line reflects the geometry-aware default.
- Nothing is hidden or disabled.

---

## Section 4 — UI surfaces

(All Textual screens keep the codebase rule: **no SpikeInterface / no
`probeinterface` import in the TUI process** — they call controller methods that
return plain data.)

### First-run

After the existing `WelcomeScreen`, a new **`ProbeSetupScreen`** (gated by
`seen_probe_setup` in `.si_menu.json`, set true on dismiss): pick a built-in
standard profile, open the full manager, or **"Skip — use placeholder for now"**
(keeps `independent`). Reuses `ChoiceModal`-style layout.

### Dashboard

- A third banner line **PROBE** under DATA / SORT:
  `PROBE  ▸ <active label> · <N> ch · <layout/pitch> · <fit summary>`.
  It joins the existing responsive yield order (the crest still drops first, then
  the PROBE/banner chrome yields under height pressure) so the lists never clip —
  re-pinned by the never-clip Pilot tests.
- New **`p`** hotkey and a **Probe** entry in the ACTIONS pane both open the
  manager.

### `ProbeManagerScreen` (modeled on `ManageSortersScreen`)

Lists all profiles (active marked with the `▌`/reverse-chip treatment), each with
its `summary()` and a channel-match flag vs. the loaded recording. Keys:
`enter` activate · `n` new (→ kind picker → editor) · `e` edit · `g` duplicate ·
`x` delete (user profiles only, **confirmed** via `ChoiceModal`) · plus "Add from
catalog" (manufacturer → model pickers) and "Import file" entries · `r` reload.

### `ProbeEditorScreen` (modeled on `ParamEditorScreen`)

Edits the kind-specific params (scalars inline; numeric validation), shows a live
`summary()` line as values change, `Ctrl+S` save / `Esc` cancel. Saving a
built-in offers to save as a copy (built-ins stay immutable).

### INSPECTING panel

Sorter rows gain the "Fit for <probe>" line (Section 3). When focus is on a probe
context (manager), the panel shows full geometry detail (`summary` + features).

### Fallback (non-Textual) menu

Parity via `ui.select` / prompts: a typed **Probe** option to list / activate /
add / edit / delete profiles, and the per-sorter fit reason folds into the
existing action/hint text. `ui.HELP_TOPICS` gains a **Probe geometry** topic
(shared by Textual Help and the typed fallback).

---

## Section 5 — Built-in presets

`probes.py: BUILTINS` (ordered; the recording's real probe first / default, then
the placeholder, then standards). Each carries a `note` and a `density_class` is
derivable so the fit engine can rank against it.

**Default (this recording's real probe — user-confirmed):**
- **`nnx-a1x16-3mm-100`** *(default)* — NeuroNexus **A1x16-3mm-100-703**: 16 sites,
  single shank, **100 µm pitch**, ~30 µm contacts → `density_class = sparse`. Maps
  1:1 onto channels `raw 1`–`raw 16` (the 6 `analog` aux channels are dropped). At
  100 µm pitch (sparse) the geometry-aware ★ sorter default stays `tridesclous2`.

**Generic / standard:**
- **`independent`** — placeholder, auto-sizes to N channels, 250 µm column. The old
  default; `density_class = independent`. Use when a recording's probe is unknown.
- **`linear-16-50um`**, **`linear-32-25um`** — single-shank dense linear.
- **`tetrode-4`** — 4 tetrodes (16 ch), 25 µm within / 300 µm between.
- **`grid-8x4-50um`** — generic dense 2-D grid.
- **`utah-10x10-400um`** — Blackrock Utah array (10×10, 400 µm pitch). Flagged:
  at 400 µm it's `density_class = independent` (electrically independent).

**Cui-lab-attested (opt-in; from published Methods):**
- **`cui-flexible-16-300um`** — custom flexible polyimide MEA: 16 recording sites,
  single shank, **300 µm pitch** → `independent`.
- **`cui-transparent-4x4-200um`** — custom transparent MEA: 16 sites, **4×4 grid,
  200 µm pitch** → `independent`.

The `probeinterface` catalog (NeuroNexus, Cambridge NeuroTech, etc.) is also
reached **live** via `catalog_manufacturers()` / `catalog_models()` for any model
not in `BUILTINS` (e.g. to pull the exact NeuroNexus site-permutation rather than
the parametric 100 µm linear approximation). The `ProbeEditorScreen`/Help shows the
**NeuroNexus name decoder**:
`A{shanks}x{sites/shank}-{length}-{pitch_µm}-{site_area_µm²}` (e.g.
`A1x16-3mm-100-703` = 1 shank, 16 sites, 3 mm, 100 µm pitch, 703 µm²/~30 µm-⌀ sites).

> Presets are starting points; every one is copy-to-edit. The default is this
> recording's confirmed probe; the first-run prompt highlights it and lists the
> other named
> profiles below it.

---

## Section 6 — Testing

- **`tests/test_probes.py`** (pure logic, following `tests/test_sorters.py`):
  schema round-trip via a temp `probes.json`; parametric builders produce the
  expected contact counts / pitch / span; `geometry_features` classification
  (independent / sparse / dense); channel-count mismatch raises; `fit()` returns
  the expected rank per geometry class; built-ins are non-deletable.
- **Textual Pilot tests** (following `tests/test_menu_app.py`): `ProbeSetupScreen`
  first-run gating (`seen_probe_setup`), the PROBE banner renders and yields under
  height pressure, `ProbeManagerScreen` activate/new/edit/delete flows, the `p`
  hotkey. `FakeController` (in `tests/conftest.py`) gains the new probe methods
  (`probe_library`, `active_probe`, `set_active_probe`, `probe_summary`,
  `sorter_fit`, …) returning canned data so the TUI tests stay SI-free.
- **`tests/test_run_sorting.py`**: `--probe` resolves and threads through; the
  controller's `sort_command` includes `--probe <active>`.
- **`tests/test_menu_controller.py`**: active-probe persistence and the
  geometry-aware `_catalog()` re-rank.

---

## Section 7 — Back-compat & migration

- **Deliberate behaviour change (user-requested):** a fresh clone / existing user
  with no `active_probe` now defaults to `nnx-a1x16-3mm-100`, so the **sort applies
  real 100 µm linear geometry** instead of the placeholder. This is verified to
  match the recording (16 neural channels), and at the `sparse` class the ★ sorter
  default is unchanged (`tridesclous2`), so the *sorting result* is unaffected — only
  the (previously non-physical) spatial geometry becomes real. Anyone who prefers
  the old behaviour selects `independent`.
- No `probes.json` ⇒ only built-ins; the file is created on first user save.
- `attach_dummy_probe` stays (now the `independent` build path) so any external
  caller/notebook keeps working; `read_broadband(attach_probe=True)` is unchanged.
- The geometry caveat text stays for `independent`; for a real probe (the new
  default) it becomes the calm "geometry: <label>" note.

---

## Appendix — Research notes (Tracy Cui lab, UPitt)

Findings from a verified web-research pass (June 2026). Two load-bearing claims
were independently confirmed against primary sources; confidence levels noted.

### §1 — Acquisition & probes (well-supported)

- **The Cui lab records on Tucker-Davis (TDT), not Blackrock/Ripple.** TDT RX5 +
  16-ch Medusa preamp @ 25 kHz (Malekoshoaraie et al. 2024, Cui co-author); TDT
  RX7 @ 24,414 Hz (Kozai et al.). No evidence of Ripple/Plexon/Intan in their own
  recordings. Their only Blackrock link is an *explant analysis* of human Utah
  arrays, not a Blackrock DAQ.
- **Cui-lab recording probes** are single-shank / fiber-bundle, low-to-moderate
  density, 6–16 recording channels — **not** dense Neuropixels-style, **not**
  22-channel:
  - NeuroNexus **A1x16-5mm-100-703-CM16** — 16 sites, 1 shank, 100 µm pitch, ~30 µm
    sites (commercial stiff control).
  - Custom **flexible polyimide MEA** — 16 recording sites, 1 shank, 300 µm pitch,
    35 µm PEDOT/CNT sites.
  - Custom **transparent MEA** — 16 sites, 4×4 grid, 200 µm pitch (ephys + 2-photon).
  - Custom **glassy-carbon SU-8 MEA** — 6 sites, 1 shank.
  - **Carbon-fiber thread array (CFET)** — 8–16, fiber bundle (~7 µm fibers).
  - **Floating microelectrode array (FMA, Microprobes)** — 16/32, small 2-D
    bed-of-nails, 400 µm pitch.

### §2 — The 22-channel puzzle (`PFCM7_d0ephys_Block2`) — RESOLVED

**Resolved from the data** (channel names read directly from the `.ns5`): the 22
broadband channels are `raw 1`…`raw 16` (the **16 electrode channels of a
NeuroNexus A1x16-3mm-100-703**, user-confirmed) plus `analog 1`…`analog 6` (6
aux channels, dropped by `neural_channel_ids` before sorting → 16 neural channels).
So it was never a 32-site front-end (the earlier inference) and the acquisition rig
is Blackrock/Ripple, not TDT. The probe is a 16-site single-shank linear array at
100 µm pitch — the `nnx-a1x16-3mm-100` default. ("PFC" = prefrontal cortex; "M7"
remains an unverified label, not load-bearing.)

### §3 — Default profiles chosen (see Section 5)

`nnx-a1x16-3mm-100` (default, = this recording's confirmed probe) + `independent`
(placeholder, for unknown geometry) + standard generators + the two Cui-attested
custom MEAs. The exact NeuroNexus site permutation can be built live from the
`probeinterface` library (the parametric default is a 100 µm linear approximation).

### §4 — Sorter ↔ geometry mapping (well-supported; backs Section 3)

- **Independent / no map / Utah 400 µm / dummy probe** → tridesclous2,
  mountainsort4/5, waveclus, spykingcircus2, simple, lupin. Poor: kilosort,
  herdingspikes, ironclust (need shared-waveform spatial info).
- **Tetrodes / monotrodes** → mountainsort4 (best at low counts), tridesclous,
  waveclus. Poor: kilosort, herdingspikes, ironclust.
- **Low-density linear (50–100 µm)** → tridesclous2, mountainsort4/5,
  spykingcircus2. Poor: herdingspikes (poor above ~60 µm).
- **Moderate/high-density linear or 2-D, real coords (≤~60 µm; Neuropixels 20 µm)**
  → kilosort 2.5/3/4, ironclust, herdingspikes2, spykingcircus2, mountainsort5.
  Poor: waveclus.
- **Drifting high-density** → kilosort 2.5+, ironclust, mountainsort5.

This squares with the workspace: the dummy independent-channel probe puts the data
in the independent class, so the runnable set (tridesclous2, spykingcircus2, lupin,
simple) is exactly right; dense-geometry sorters are mismatched until a real probe
is supplied.

### §5 — Confidence

- **Verified from the data + the user:** this recording's probe is a NeuroNexus
  **A1x16-3mm-100-703** (16 sites, 100 µm) on channels `raw 1`–`raw 16`, with 6
  `analog` aux channels dropped → 16 neural channels. This is the default profile.
- **Verified from research (background, for the other presets):** the Cui lab's
  *published* probes (A1x16, custom flexible/transparent MEAs) and the
  sorter↔geometry mapping that backs Section 3.
- **Superseded inference:** the earlier "22 = a 32-site front-end subset" guess —
  resolved by §2 (it's 16 electrodes + 6 aux).
- **Speculation (labelled):** "M7" = mouse #7 (not load-bearing).

### Sources

Cui probes/acquisition: PMC12994769 · nature.com/articles/s41378-024-00685-6 ·
PMC11211464 · PMC4688254 · PMC11421982 · PMC10591823 · PMC10153108 ·
engineering.pitt.edu/people/faculty/xinyan-tracy-cui.
Commercial probes / probeinterface: probeinterface.readthedocs.io
(ex_10_get_probe_from_library) · cambridgeneurotech.com/neural-probes ·
blackrockneurotech.com/products/utah-array · microprobes.com (FMA) ·
NeuroNexus naming (LinkedIn, A. Paez).
Systems / 22-ch reasoning: rippleneuro.com (Nano2) · Blackrock Cerebus IFU.
Sorters/geometry: Kilosort (Neuron S0896-6273(22)00448-2; github MouseLand/Kilosort
v3) · HerdingSpikes (github mhhennig/hs2) · IronClust (github flatironinstitute) ·
MountainSort4 (eLife 55167) · Tridesclous docs · WaveClus (PMC6230803) ·
SpikeInterface sorters docs.
