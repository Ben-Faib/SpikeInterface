# Audit findings - 2026-07-13

Issues surfaced while rewriting `CLAUDE.md`. Every claim in the old `CLAUDE.md` was
checked against the source; these are the places where the code, its comments, and its
docs had drifted apart. Nothing here has been fixed - this is a work list.

Each finding carries the evidence that produced it. Line numbers are as of commit
`4807ce0`.

| # | Finding | Severity | Where |
|---|---|---|---|
| 1 | CLI sorts ignore the menu's active probe | **Behaviour gap** | `run_sorting.py:698`, `SpikeInterface_Menu.py:1113` |
| 2 | `run_info.json` doesn't record the probe actually used | **Provenance gap** | `run_sorting.py:433` |
| 3 | Duplicate `"probe"` key in one dict literal | Latent bug | `run_sorting.py:437`, `:440` |
| 4 | `read_events` is documented "best-effort" but has no error handling | Latent bug | `blackrock_io.py:318` |
| 5 | `return_in_uV=True` rides an unpinned upstream default | Latent risk | `run_sorting.py:1040` |
| 6 | Non-TTY bare run silently builds the report | Undocumented behaviour | `SpikeInterface_Menu.py:1343` |
| 7 | `attach_a1x16_probe()` + `A1X16_*` are dead code | Dead code | `blackrock_io.py:198–231` |
| 8 | `DataSetupScreen` is dead code | Dead code | `menu_app.py:206` |
| 9 | `run_sorting.py` module docstring is stale in two ways | Stale docs | `run_sorting.py:28–34` |
| 10 | `blackrock_io` comment misstates why only one stream selector is passed | Stale comment | `blackrock_io.py:143` |
| 11 | Responsive breakpoint half-constant, half-magic-number | Cosmetic | `menu_app.py:1843` |
| 12 | `c` means two different things in two modals | Cosmetic / UX | `menu_app.py:758`, `:947` |

---

## 1. A bare CLI sort ignores the menu's active probe - **Behaviour gap**

`resolve_probe()` falls back to `probes.DEFAULT_PROBE` and **never reads
`.si_menu.json`**, so the `active_probe` the user picked in the menu is invisible to the
CLI:

```python
# scripts/run_sorting.py:698-708
def resolve_probe(name, probe_file):
    ...
    return probes.get(name) if name else probes.get(probes.DEFAULT_PROBE)
```

The menu only gets the right answer because it papers over this by passing the probe
explicitly on every invocation:

```python
# SpikeInterface_Menu.py:1113
argv += ["--probe", self.active_probe]
```

**Why it matters.** `show_channels.py` *does* honour the setting
(`show_channels.py:53` reads `cfg.get("active_probe")`). So today, after a user selects a
non-default probe in the menu:

- `probe_map.png` is drawn with the **selected** probe,
- a bare `uv run python scripts/run_sorting.py` sorts with the **default** probe,

and the two silently disagree. Anything else that shells out to `run_sorting.py` without
passing `--probe` inherits the same bug.

**Suggested fix.** Give `resolve_probe()` the same fallback chain `show_channels.py`
uses - `--probe-file` → `--probe` → `.si_menu.json`'s `active_probe` →
`probes.DEFAULT_PROBE` - and then drop the menu's compensating `--probe` push (or keep it;
it becomes a harmless no-op). This makes `.si_menu.json` the single source of truth for the
active probe, which is what the probes layer was built to be.

---

## 2. `run_info.json` records the probe *argument*, not the probe *used* - **Provenance gap**

```python
# scripts/run_sorting.py:433-441
info = {
    ...
    "probe": args.probe,          # None on a default run
    ...
}
```

`run_info.json` exists so downstream surfaces can tell one run apart from another. But it
stores the raw `--probe` **argument**, which is `None` for a default run - so a default
run's provenance never says `nnx-a1x16-3mm-100`. It also won't record the fallback when the
default probe doesn't fit and the code silently drops to the `independent` placeholder
(`run_sorting.py:918-922`).

**Suggested fix.** Record the *resolved* profile name (and whether it was a fallback), not
the argument. This is a prerequisite for trusting any cross-run comparison - and it pairs
naturally with finding 1.

---

## 3. Duplicate `"probe"` key in `_write_run_info` - Latent bug

```python
# scripts/run_sorting.py:437 and :440 - same dict literal
    "probe": args.probe,
    "n_jobs": args.n_jobs,
    "probe": getattr(args, "probe", None),   # silently overwrites :437
```

Both expressions evaluate to the same value today, so there is no behavioural bug - but
the second key silently shadows the first, it's clearly an editing leftover, and any linter
(ruff `F601`/`B035`) will flag it. Delete line 440. Fixing finding 2 removes it anyway.

---

## 4. `read_events` is documented "best-effort" but has no error handling - Latent bug

The docstring promises best-effort behaviour:

```python
# scripts/blackrock_io.py:318
"""Best-effort read of digital/serial event markers stored in the ``.nev``.
```

But the body (`blackrock_io.py:325-342`) has **no `try`/`except`**. `parse_header()` or
`get_event_timestamps()` raising will propagate straight to the caller. The `[]` return
happens only when the file genuinely has no event channels - it is not a failure path.

**Why it matters.** Callers were told they could trust it, and `report.py` relies on the
whole-loader-per-try/except pattern to turn a failure into a SKIP row rather than a crashed
report. Either the code or the docstring is lying; pick one.

**Suggested fix.** Wrap the neo calls and return `[]` on failure (matching the docstring),
*or* drop "best-effort" from the docstring and make every caller wrap it. The former is
closer to the surrounding design.

---

## 5. `return_in_uV=True` rides an unpinned upstream default - Latent risk

`sort_summary.compute_summary()` correctly gates on `analyzer.return_in_uV` before deciding
whether to apply the channel gain (`sort_summary.py:131-149`) - this is the guard that
prevents the µV double-scaling bug. But `run_sorting.py` **never passes `return_in_uV`
explicitly** when building the analyzer (`run_sorting.py:1040-1043`); it inherits
SpikeInterface's signature default (`create_sorting_analyzer(..., return_in_uV=True)`).

**Why it matters.** A silent upstream flip of that default would change the units of
`templates`/`noise_levels`. The gate would still catch it - that's the point of the gate -
but relying on an unpinned third-party default for a units invariant is worth removing.

**Suggested fix.** Pass `return_in_uV=True` explicitly at the `create_sorting_analyzer`
call site. One keyword, and the invariant stops depending on someone else's default.

**Regression canary** (worth keeping in any test): the noise floor is a property of the
*recording*, not the sorter, so it must land at ~4 µV for **every** sorter - observed
3.88–4.02 µV across all 8 saved sorts, all with `gain_to_uV: 0.249977`. A reading near
**1 µV** means the gain got re-applied.

---

## 6. A bare run on a non-TTY silently builds the report - Undocumented behaviour

```python
# SpikeInterface_Menu.py:1343-1345
if not sys.stdin.isatty():
    ui.note("(non-interactive stdin -> building the report)")
    return 0 if DISPATCH["report"](args) else 1
```

Running `SpikeInterface_Menu.py` with no action under a pipe, in CI, or from any
non-interactive context does **not** open the dashboard and does **not** no-op - it runs the
`report` action, which loads the recording and writes `outputs/report.html`.

This is defensible behaviour, but it is surprising, undocumented, and means a stray
scripted invocation does real work. It is now noted in `CLAUDE.md`. Worth deciding whether
a non-interactive bare run should instead print usage and exit.

---

## 7. `attach_a1x16_probe()` and the `A1X16_*` constants are dead code

`blackrock_io.py:198-231` defines `A1X16_N_CONTACTS`, `A1X16_PITCH_UM`, and
`attach_a1x16_probe()`. Grepping the whole repo - `scripts/`, `tests/`, `notebooks/`, the
launcher - finds **zero call sites outside `blackrock_io.py` itself**. `probes.py`
superseded it: the NeuroNexus geometry now lives in `probes.BUILTINS` as
`nnx-a1x16-3mm-100`, and the sort applies it via `probes.build()` → `set_probe()`.

Leaving it in place is actively harmful: it is a plausible-looking function that a reader
(or Claude) will naturally build on, bypassing the probes layer that is supposed to be the
single source of truth for geometry. The old `CLAUDE.md` in fact pointed at it.

**Suggested fix.** Delete all three, or reduce to a one-line deprecation pointing at
`probes.py`.

---

## 8. `DataSetupScreen` is dead code

`menu_app.py:206` defines `class DataSetupScreen(ModalScreen)`, with ~14 lines of its own
CSS. It is never `push_screen`ed anywhere - not in `menu_app.py`, not in the launcher, not
in the tests. It was behaviourally replaced by the `HelpScreen`'s `data` topic
(`action_data_help` → `HelpScreen(..., topic="data")`, `menu_app.py:2489`), but the class
was left behind.

**Suggested fix.** Delete the class and its CSS block.

---

## 9. `run_sorting.py`'s module docstring is stale in two ways

```python
# scripts/run_sorting.py:28-34
... an "independent channels" probe is attached (see blackrock_io.attach_dummy_probe).
...
Installed CPU sorters are tridesclous2 and spykingcircus2 ...
```

Both sentences are now wrong:

- The sort does **not** attach the independent-channel probe by default. It passes
  `attach_probe=False` and applies the active probe from `probes.py` - which defaults to the
  real NeuroNexus A1x16. The placeholder is only a *fallback* when the default doesn't fit.
- There are **four** locally installed sorters, not two: `tridesclous2`, `spykingcircus2`,
  `lupin`, `simple` (all of SpikeInterface's internal sorters, verified via
  `ss.installed_sorters()`).

This matters more than a normal stale comment, because the new `CLAUDE.md` explicitly tells
readers to trust module docstrings over the guidance file. That contract only holds if the
docstrings are true.

---

## 10. `blackrock_io` misstates *why* only one stream selector is passed - Stale comment

The comment at `blackrock_io.py:143-145` justifies `read_lfp`'s single-selector call by
saying SpikeInterface *rejects* receiving both `stream_id` and `stream_name`. Against the
installed SpikeInterface 0.104 that is false:

```python
# .venv/.../spikeinterface/extractors/neoextractors/neobaseextractor.py:214  (SI 0.104.3)
assert stream_id or stream_name, "Pass either 'stream_id' or 'stream_name"
```

It asserts only that **at least one** is given; passing both is silently accepted, with
`stream_name` winning. The *practice* (pass exactly one, normalise to `stream_id`) is still
right - only the stated reason is wrong. Left as-is, the next person to touch stream
selection will reason from a false premise.

---

## 11. Responsive breakpoint is half-constant, half-magic-number - Cosmetic

```python
# scripts/menu_app.py:1843
hide_inspect = h < (self.STACK_SHORT_ROWS if stacked else 16)
```

`STACK_COLS` (64), `STACK_SHORT_ROWS` (24), and `TINY_ROWS` (14) are all named constants
(`menu_app.py:1870-1876`), but the side-by-side threshold is a bare `16` inline. Promote it
to a named constant alongside the others.

---

## 12. `c` means two different things in two modals - Cosmetic / UX

- `DownloadProgressScreen` (`menu_app.py:758`): `c` = **collapse** the download view.
- `ManageSortersScreen` (`menu_app.py:947`): `c` = **clear saved sort** (destructive; it does
  confirm first).

Same key, unrelated meanings, in two screens a user moves between while managing sorters.
The confirm dialog makes this safe rather than dangerous, but it's a trap worth renaming
one side of.

---

## Resolved by the same pass

`CLAUDE.md` itself was the largest source of drift and has been rewritten (4,592 → 1,720
words). Claims that were **wrong**, now removed or corrected:

- "There is no package, no test suite, and no build step" - there are 256 passing tests.
- "The Textual process imports no SpikeInterface" - true of the *module*
  (`scripts/menu_app.py`), false of the *process*: `MenuController` imports SpikeInterface
  during startup, before the first frame paints.
- "The inspector is the console command `sigui <analyzer_dir>`" - no `sigui` CLI is invoked;
  it's an in-process `sigui.run_mainwindow(...)` call, and the child process is the launcher
  re-invoking itself.
- The µV double-scaling note had the direction inverted (re-applying a 0.25 µV/count gain
  makes values ~4× *too small*, not too large).
- It documented `attach_a1x16_probe()` - dead code (finding 7).

The largest *omission*, now fixed: nothing in the old `CLAUDE.md` mentioned that only 16 of
the recording's 22 channels are neural, or that the sort drops the 6 `analog N` aux channels
before referencing - the fact that drives both the aux-drop and the 16-contact probe.
