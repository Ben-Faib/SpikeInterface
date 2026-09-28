# GOAL V2 - Spike 2.0: the journey rail, every setting editable, values reproducible

Ben, 2026-09-27: "Build it and then test please" (the v2.0 mockups canvas,
https://claude.ai/artifact/EUoxskhq7QZi1QYMVGMBrf), plus "make it clearer how to edit probe
settings and all other settings need to be more clearly editable" and "I want to be able to
reproduce values as well". This is the W3 face pick in practice: the terminal workbench,
reshaped around the researcher's journey. Decisions of record below supersede DESIGN_UX §2
(F2's fourteen-row list) and the "1-6 keep their historical meanings" rule.

## Intent

A lab member opens the tool and always knows three things without reading a manual: where
this recording stands (the rail), the one thing to do next (the next-step card), and how to
change anything (every setting is a visible, editable row that says where it is saved and
what it affects). Any number the tool shows can be reproduced: the run that made it carries
its complete recipe, and one action re-runs that recipe and scores the new values against
the old ones with stated tolerances.

## The shape (decisions of record)

- **The rail**: six stages, always on top: `1 Data · 2 Probe · 3 Sort · 4 Judge · 5 Apply ·
  6 Share`, each with a state mark (done ✓ green / needs attention ! amber / to do · dim /
  current = accent chip) and a one-line caption. Stage state is computed by the controller
  (`stage_status()`), never by the view.
- **Home** = the rail + a NEXT STEP card (`next_step()`: title, why, the action it runs) +
  WHERE THINGS STAND (recording, probe, sort, health canary, judged, manual match) + the
  probe map (units at their contacts) + RECENT (run store + last results). Narrow terminals
  drop the probe map, then RECENT; 80x24 shows everything else without scrolling.
- **Stage panes** (content switches under the rail; no modal stack for navigation):
  1 Data (files, folder, streams, explore, traces, install check, first-run guidance) ·
  2 Probe (active probe drawn as a shank with its values; library; edit/new/duplicate/
  import/delete - every probe value visible and editable) · 3 Sort (sorter list ranked for
  this probe with last results, how much, the settings the next sort will use, start) ·
  4 Judge (queue flagged-first, unit card with evidence: waveform on neighbouring contacts,
  ISI histogram with the refractory window, amplitude over time; g/m/n/u verdicts) ·
  5 Apply (before/after, the decision log, apply in-app) · 6 Share (every output with its
  freshness: report, comparison, shootout, explore page, Phy export, GUI inspector, values
  CSV, run recipe, reproduce).
- **Settings** (`,` from anywhere, also a palette entry and a Home link): ONE screen listing
  every setting in groups - Recording, Probe, Signal before sorting (band-pass low/high,
  bad-channel detection on/off + method, always-exclude channels, keep aux channels),
  Sorter (active sorter, parameters, quick-test length, CPU jobs, Docker sorters),
  Quality rule (SNR >=, ISI ratio <=, amplitude cutoff <=, presence >=), Appearance. Each
  row: name, current value, default when changed, what it affects. ↵ edits in place (typed
  input with validation, toggle, or choice); `d` resets to default. Values persist to
  `.si_menu.json`; every sort passes them as run_sorting flags and records them in
  run_info.json. The screen says both facts.
- **Reproduce**: a Runs & reproducibility screen (from Share, Sort result and the palette):
  every saved run of the active sorter (id, date, span, units, noise floor, current mark);
  for the selected run its recipe (sorter, effective params, seed, probe + geometry hash,
  preprocessing chain, package versions, git sha); actions: re-run from recipe (runs.py
  regenerate in a subprocess, never touching `runs/` or the current pointer) then show the
  match report criterion by criterion (recorded vs regenerated, tolerance, verdict); export
  the recipe file; make a run current (smoke rule respected).
- **Palette** (`/`): type to find any action by name; shows which stage it lives in.
- **Keys**: global `1`-`6` stages, `↵` next step (Home) or the pane's primary action,
  `Esc` back to Home (a no-op on Home - it never exits), `/` find, `,` settings, `?` help,
  `q` quit. Letters act only inside the pane that shows them; a destructive action always
  confirms. Every key a pane accepts is printed on that pane's key line.
- **Launch**: a short splash (wordmark + the real startup checklist); any key skips it;
  never shown in tests or on a non-TTY.

## Addendum 2026-09-27 (Ben): the terminal is the control surface, not the evidence

Character-cell waveforms are a glance, too coarse to judge a unit by. 4 Judge keeps
them, labelled "at a glance", and `v` opens the unit in `units.html` (one per run,
`scripts/unit_page.py`): stored spikes over the template on nearby contacts,
autocorrelogram and ISI with the refractory window, amplitude over time with its
distribution, PC1/PC2 against the most similar unit, and their cross-correlogram.
Labelling stays in the terminal.

## Boundaries

- The view imports no SpikeInterface (unchanged). New data the view needs arrives as plain
  data from the controller; SI-dependent computation lives in scripts modules
  (`unit_evidence.py` for the judge card).
- Every invariant in CLAUDE.md holds: aux drop first, bad channels before CMR, runs never
  clobber, smoke rule, µV gate, `--progress json` purity, metrics non-fatal.
- Nothing hardcodes 16/22 channels, a sorter list, or a path outside `runs.sort_paths()`.
- No em dashes anywhere.

## Definition of done

1. The app launches into v2 on the real data; all six stages, Settings, Palette, Runs and
   the splash render at 100x34 and 80x24 without clipping or exceptions.
2. Every setting listed above is editable in-app, persists, and reaches the next sort's
   argv (pinned by tests) and its run_info.json (checked on a real smoke sort).
3. Probe: every value of the active probe is visible on the Probe pane, and edit / new /
   duplicate / import-from-file / delete / activate work in-app.
4. Judge shows real evidence per unit; labels land in the curation record; Apply builds the
   curated result in-app; Share opens/rebuilds every output.
5. Reproduce: re-running the current run from its recipe shows a match report in-app with
   the noise-floor canary within tolerance.
6. `scripts/check_workbench.py` drives every function against the real recording in an
   isolated sandbox (never touching the real outputs, record or settings) and prints one
   pass/fail line per function; it is green on this Mac and is the Windows acceptance test.
7. Gates: full suite green (old dashboard tests rewritten for v2, snapshots re-baselined
   deliberately), 30 s smoke canary ~4 µV, verify_install, the harness, one fresh-context
   review folded.
8. Docs true: WORKFLOW.md, README, Instructions.html, in-app help, CLAUDE.md, DESIGN_UX §2,
   and `docs/WINDOWS_TEST.md` (the lab-box setup + acceptance steps).
