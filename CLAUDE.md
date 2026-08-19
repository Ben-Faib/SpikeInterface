# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A single-recording SpikeInterface workspace: loaders, analysis scripts, and a
terminal front-door menu, all built around one Blackrock/Ripple recording
(`PFCM7_d0ephys_Block2`) in the repo root. It is **not a package** — there is no
install step; consumers put `scripts/` on `sys.path` and import the modules:

```python
import sys; sys.path.insert(0, "scripts")   # notebooks use Path.cwd().parent / "scripts"
import blackrock_io as bio
```

| File | Stream | Loader |
|---|---|---|
| `.ns2` | LFP @ 1 kHz (`lfp N`) | `read_lfp()` → Recording |
| `.ns5` | broadband @ 30 kHz — **the spike-sortable stream** | `read_broadband()` → Recording |
| `.nev` | online-detected spikes + digital markers, 30 kHz clock | `read_spikes()` → Sorting; `read_events()` |

**Both streams carry 22 channels, but only 16 are neural.** The other 6 are non-neural
`analog N` aux inputs (sync pulses etc., channel ids 10241+). Nothing hardcodes 16 or 22 —
the split is discovered at runtime by `bio.neural_channel_ids()`. This one fact drives the
aux-drop and probe invariants below; internalise it before touching the sort.

Raw data is git-ignored (the `.ns5` is ~176 MB, over GitHub's 100 MB limit), so a fresh
clone has no data. Loaders auto-discover any Blackrock file set by base name; a missing
set surfaces as a clear `FileNotFoundError` from `find_blackrock_base()`.

## Orchestration — how build work runs here (installed 2026-08-18, decantv2 pattern)

The workbench is being built into a lab tool for Tracy's UPitt lab via loop engineering.
Read order for a build session: `NORTHSTAR.md` (product + decisions of record, wins
conflicts below it) → `LOOPS.md` (method + gates) → the active brief in `goals/` →
`ROADMAP.md` (the live queue Ben pastes prompts from — keep its NOW box and constants true;
a stale marker is a defect). Sessions touching any UI surface additionally read
`DESIGN_UX.md` — the design authority; its §1 language binds all surface work.
Conversational/small-fix sessions don't need any of it.

**The between-run contract.** Every phase/slice run ends **sealed**: work committed with a
descriptive message (explicit paths — see concurrent-edit rule below), ROADMAP.md updated,
any surprise worth keeping written to `LESSONS.md` (one lesson per entry, encode the fix
into a skill or brief), and **one five-line block appended to `SEALS.md`** — what you did,
what it means, what moved, what needs Ben, what is next, one sentence each. Update SEALS.md's
pinned "Where we stand" lines if your work changed one; add/close OPEN items. `/status`
reads SEALS.md and reports nothing that is not in it. Git history + those files are the
state tracker — a fresh session re-enters by reading them, never by asking Ben what
happened. A run that stops short commits partial state and says plainly what is done, what
is not, and why.

**Verification is the `verify-spike` skill** (change-type → gates; the ~4 µV noise-floor
canary is a verdict). **Substantive slices get one fresh-context Fable review** of the full
diff against the brief and this file's invariants before sealing (the `reviewer` agent —
reviews always run on Fable); findings addressed or recorded. No stacked self-verification
beyond that. Agents: `scout`/`builder` on Opus, `reviewer`/`finalizer` on Fable; workflow
`agent()` calls pass `model` explicitly. The closing chat summary says the same five things
as the SEALS block and stops — under 200 words; the long version already exists on disk.

## Commands

```bash
uv sync                                     # env (Python 3.12); conda fallback: environment.yml
uv sync --group dev                         # + pytest
uv run python SpikeInterface_Menu.py        # front door: dashboard
uv run python SpikeInterface_Menu.py sort   # ...or dispatch one action directly
uv run python -m pytest tests/              # Textual Pilot tests for the menu + unit tests
uv run python scripts/verify_install.py     # smoke test: versions + all three loaders
uv run python scripts/run_sorting.py --duration 30   # quick sort smoke test (first 30 s)
```

Menu actions: `explore | sort | report | gui | traces | compare | verify`.
`verify_install.py` is the loader smoke test — run it after changing `blackrock_io.py`.

Scripts document their own flags in their module docstrings (kept current — read those
rather than a list here). `compare.py`'s flags: `--online SORTER` (offline sort vs a
sorted .nev reference; flagless = the two-sorter page), `--nev PATH` (an explicit
re-exported .nev, e.g. a manual sort), `--delta-ms` (coincidence window — the online
default is deliberately wide, crossing-stamps lead peak-aligned spikes ~0.6 ms here);
`make_report.py` is a thin shim
that forwards argv to the launcher's `report` action.

## Where things live

Each `scripts/` module is a **single source of truth**. Extend it; don't re-implement or
hardcode around it. Read a module's docstring for its API — they are thorough and stay in
sync with the code, which is why this file does not restate them.

| Module | Owns | Don't instead |
|---|---|---|
| `blackrock_io.py` | loading this dataset | open the files with neo/SI directly |
| `sorters.py` | which sorters exist / are runnable, params, Docker | hardcode a sorter list |
| `probes.py` | electrode geometry (profiles, active probe, sorter fit) | build a `Probe` inline |
| `sort_summary.py` | the six array/yield metrics | recompute amplitudes ad hoc |
| `sort_progress.py` | the JSON event protocol between `run_sorting` and the TUI | print status for the UI to scrape |
| `run_sorting.py` | the sort pipeline + its terminal presentation | |
| `report.py` | self-contained `outputs/report.html` (Plotly inlined) | |
| `ui.py` | shared rich styling, themes, fallback-menu widgets | |
| `menu_app.py` + `SpikeInterface_Menu.py` (root) | Textual dashboard (view) + controller (data/actions) | |

The six metrics `sort_summary` owns: **V_pp**, **SNR**, **noise floor**, **yield**
(% of electrodes that are peak channel of ≥1 unit), **units/ch**, **units/active-ch**.
They surface in four places — the `run_sorting` terminal card, `report.html`, the menu's
RESULTS section, and `comparison.html`. Change the computation in one place only.

## Invariants that bite

Things that are wrong-by-default. Preserve them when editing.

### The sort pipeline

```
read_broadband(attach_probe=False) → drop non-neural aux channels → set_probe(active probe)
    → bandpass_filter(300–6000) → detect + drop bad channels → common_reference(global, median)
    → run_sorter → save Sorting, then build SortingAnalyzer + metrics → outputs/<sorter>/
```

- **Aux channels are dropped first** (`bio.neural_channel_ids()` + `bio.select_channels()`;
  keep them with `--keep-analog`). The ordering *is* the point: aux channels would poison the
  common median reference that every neural channel is referenced against, and make the sorter
  emit spurious units. Any new sort-adjacent code must drop them too.
- **Bad channels leave before the CMR too** (PRE1, 2026-08-18): `detect_bad_channels`
  (method `mad`, seed + threshold pinned for determinism) runs post-bandpass; flagged and
  `--bad-channels`-named channels are excluded from reference AND sort, geometry preserved,
  recorded in `run_info.json`'s `bad_channels` block and stated on every surface that shows
  channels/yield. Auto-detection refuses wholesale above 25% of the array; manual names
  always pass but must leave ≥2 channels. **On this recording nothing is flagged — the E1
  channel-1 pathology is sub-300 Hz, so the bandpass removes it before the median; that
  measured negative is the point, not a bug.** Note tridesclous2 is measurably
  non-deterministic on this recording (14/16/18 units across identical runs) — never treat
  unit counts/ids as stable across re-sorts.
- **The sort passes `attach_probe=False`** and applies geometry from the probes layer
  (`probes.build()` → `set_probe()`), *not* `attach_dummy_probe()`.
- **Quality metrics are non-fatal.** The Sorting is saved *before* metrics run, so a metrics
  crash degrades to success-with-note (rc 0) rather than discarding units — and the handler
  deletes the half-built `analyzer/`, `quality_metrics.csv`, `summary.*` so downstream
  surfaces never read stale derived data.
- **`--progress json` keeps stdout pure**: JSON events go to stdout; human/rich output and the
  sorters' own fd-1 writes are redirected to stderr. Never print to stdout in that mode.
- `report.py` reads sorted-unit data **only** from the saved `SortingAnalyzer`. The loose
  `outputs/<sorter>/sorting/` folder and `quality_metrics.csv` are leftovers from other runs —
  ignore them.

### µV scaling — the double-scaling trap

The `SortingAnalyzer` returns µV, so `templates` and `noise_levels` are **already scaled**.
`compute_summary` gates on `analyzer.return_in_uV` and must **not** re-apply the channel
gain. This rig's gain is `0.249977 µV/count`, so re-applying it *multiplies by 0.25* — the
bug this caused made V_pp and noise come out **~4× too small**, not too large.

Note `run_sorting.py` never passes `return_in_uV` — it rides SpikeInterface's signature
default (`create_sorting_analyzer(..., return_in_uV=True)`). That is an **unpinned upstream
default**: if SI ever flips it, the gate is what saves us, so don't remove it.

**Regression canary:** noise floor is a property of the *recording* (post-bandpass + CMR),
so it lands at **~4 µV for every sorter** (observed 3.88–4.02 across all saved sorts). If it
varies by sorter, or reads **~1 µV**, the gain has been re-applied.

### Geometry

The Blackrock files carry no probe map, so geometry is a *user choice*, owned entirely by
`probes.py`. The active probe defaults to this rig's real **NeuroNexus A1x16-3mm-100-703**
(`probes.DEFAULT_PROBE = "nnx-a1x16-3mm-100"`, 16 contacts @ 100 µm); the `independent`
placeholder (no two channels neighbours) remains available.

- **Geometry only *softly re-ranks* sorters** (`probes.fit()`); it never blocks one.
  **Sorting is not blocked on geometry — don't tell the user it is.**
- 100 µm puts this probe in the `sparse` density class, which is *why* `recommended_for()`
  keeps `tridesclous2` as the default sorter.
- **Fit failure is asymmetric by design:** an *explicit* `--probe`/`--probe-file` that doesn't
  fit is a hard error (rc 1); the *default* probe not fitting warns and falls back to the
  `independent` placeholder.
- **Gotcha — the CLI ignores your menu selection.** `run_sorting.py` resolves the probe from
  `probes.DEFAULT_PROBE`, never from `.si_menu.json`'s `active_probe`. The menu compensates by
  always passing `--probe <active>` explicitly. So a bare CLI sort and a menu sort can use
  different geometry.
- `bio.attach_a1x16_probe()` / `A1X16_*` are **dead code** superseded by `probes.py` — don't
  build on them.

### Loaders (`blackrock_io.py`)

- **neo file sets:** neo keys on the filename *without* extension (`foo.nev` + `foo.ns2` +
  `foo.ns5` = one set). Pass `find_blackrock_base()`'s extension-less stem to
  `read_blackrock`/`get_neo_streams`. `read_spikes` is the exception — it appends `.nev`.
  Discovery prefers a stem that carries `.nsX` data (a stray/extra `.nev` beside the set —
  e.g. a manual re-export — can never be picked by sort-order luck), falls back to a lone
  `.nev` only when no analog data exists, and **refuses honestly, naming the candidates**,
  when several sets are genuinely ambiguous (callers degrade via `FileNotFoundError`).
- **Stream selection:** pass exactly **one** selector. `read_lfp` normalises to `stream_id`
  and leaves `stream_name=None`. (An in-code comment claims SI *rejects* receiving both — that
  is stale: SI 0.104 only asserts at least one is given, and `stream_name` silently wins.
  Passing one selector is still the rule; the stated reason is just wrong.)
  `read_broadband` picks the **highest-rate** stream and raises below 10 kHz (i.e. when only
  LFP is present).
- **NEV clock:** spike sample indices → seconds via `NEV_TIMESTAMP_RATE = 30_000.0`.
- **`set_probe()` returns a new recording** — it does not mutate in place.
- **Events are *not* actually best-effort**, despite the docstring: `read_events` has no
  internal try/except, so a neo parse failure **propagates**. It returns `[]` only when there
  are genuinely no event channels. Callers must wrap it.
- **Blackrock unit ids** — semantics owned by `blackrock_io` (`unit_class`,
  `UNIT_CLASS_LABELS`, `online_unit_labels`; consumed by compare/explore from that one
  home): `0` = unsorted threshold crossings, `1..n` = online-sorted units,
  `255` = noise/invalidated.

### Sorters

- The four locally-runnable sorters (`tridesclous2`, `spykingcircus2`, `lupin`, `simple`) are
  SpikeInterface's own **internal** sorters — they need no external binary, so they are always
  installed. Everything else needs Docker or a GPU.
- **Docker is only a fallback for sorters you don't have** (`sorters.uses_docker()`): an
  installed sorter runs natively even with Docker on.
- **GPU sorters** (kilosort*, pykilosort, yass) are listed but never offered here — no NVIDIA
  GPU, and Docker-on-Mac has no GPU passthrough.
- `group_of()` is the *stable* grouping (daemon-independent, so a sorter never jumps groups
  when Docker starts/stops); `status()` reflects the live daemon. Don't confuse them.

### Menu

- **The view imports no SpikeInterface.** `scripts/menu_app.py` talks to `MenuController` —
  which lives in the root `SpikeInterface_Menu.py`, *not* `scripts/` — through a structural
  `Protocol`, which is why tests can inject a fake controller. Keep SI out of the view.
  (The *process* does import SI, via the controller, during startup; this is a testability
  boundary, not an import-cost claim.)
- **A bare run on a non-TTY builds the report** rather than opening the dashboard — a piped
  or CI invocation silently runs the `report` action.
- **Esc is a deliberate no-op**, so a reflexive back-press never exits the dashboard.
- Sorting runs *in-UI* via a `run_sorting.py --progress json` subprocess, never `suspend()`.
  Actions needing a fresh process re-invoke the launcher itself (`_self`).
- Responsive yield is budget arithmetic around `TINY_ROWS` (D5): chrome — crest, then
  RESULTS, then banner/manage/LAST — yields under pressure so the action list never
  clips; pinned by the painted-rows and never-clip Pilot tests.

## Conventions

- `matplotlib.use("Agg")` **before** importing pyplot; figures go to `outputs/` (git-ignored).
- Entry points: `if __name__ == "__main__": raise SystemExit(main())`, with `main()`
  returning an int — also required for `n_jobs > 1` on Windows (`spawn`).
- `pathlib` throughout (`REPO_ROOT` from `blackrock_io`); code must run on macOS/Windows/Linux.
- **Python 3.12, not 3.13** — broadest prebuilt-wheel coverage on Windows, so installs never
  need a C compiler. Enforced by `requires-python = "==3.12.*"` + `.python-version`.
  Pins that matter: `zarr<3` (SI doesn't support 3.x), `plotly<6` (report inlines
  `plotly.offline.get_plotlyjs`).
- Qt binding is **PySide6** under uv, **PyQt5** under the conda fallback — don't install both
  into one env.
- Local state is git-ignored: `.si_menu.json` (exactly `theme`, `use_docker`, `sorter_params`,
  `active_probe`, `seen_welcome`, `seen_probe_setup`, `active_sorter`, `last_result`,
  `quality_rule` — the last three added 2026-08-18 by D1/W1; `quality_rule` is READ by
  sort_summary, never written by the app yet) and `probes.json` (the user probe library).
- Tests live in `tests/`; the menu is covered by Textual `Pilot` tests. Run the whole suite
  before claiming a menu change works — the view is easy to break in ways only Pilot catches.
  A green suite still isn't the whole story for sort-adjacent changes: the real feedback loop
  is `run_sorting.py --duration 30` (plus one containerized sort when touching Docker paths).
- **The user edits this repo concurrently from other sessions.** The tree can change
  mid-session and unrelated WIP can appear even in files you're editing. Re-check
  `git status`/`git diff` immediately before committing, stage explicit paths (never
  `git add -A`), and put their unrelated changes in their own commit before yours.
