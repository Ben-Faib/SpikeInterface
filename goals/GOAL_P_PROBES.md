# GOAL P — Probe flexibility: the lab's probes differ, and the workbench must keep up

## Intent

Product fact of record (Ben, 2026-08-18): the UPitt researchers' **probes have different
setups** — a workbench locked to one array serves one experiment, not the lab. The geometry
layer (`probes.py`) already owns profiles, a user library (`probes.json`), an editor, fit
scoring, and the real NeuroNexus A1x16 default; this track generalizes it: describe, import,
verify, and switch any probe the lab actually uses. Wiring correctness is scientific
correctness — a wrong channel→site map silently corrupts every spatial result.

## Task (slices)

- **P1 — probeinterface import.** Accept standard probe descriptions — probeinterface
  `.json` (and `.prb` where probeinterface reads it), including the probeinterface library's
  published maps — into the user library via CLI and menu, with validation against the
  recording's neural channel count and honest errors naming the mismatch.
- **P2 — multi-shank / ProbeGroup support.** Geometry, fit scoring, report probe view, and
  sorter recommendations handle multi-shank layouts; density classing per shank.
- **P3 — wiring verification. CLOSED AS A WAIT (Ben, 2026-08-19): no adapter map is
  coming; channel→site identity wiring is the accepted standing assumption, reopened only
  if a map ever arrives.** The surface sketched here (view the current map, apply an
  adapter map, a data-driven sanity view of per-channel noise/amplitude by claimed depth)
  is not queued; it becomes relevant again only with a real map or a probe whose wiring is
  in doubt. **On-record items from P1's and P2's reviews (2026-08-18, also in
  probes.py's docstring):** `run_sorting.py --probe-file` (kind `file`) still applies
  identity wiring unconditionally — with the import CLI existing it is now the trap door
  for wired probes and P3 must close it; imported tetrode-style geometry
  density-classes as `dense` rather than tetrodes (soft re-rank only — mis-ranking, not
  mis-sorting); coincident-probes import error wording is true but unhelpful (two
  un-offset probes in a ProbeGroup fail as "two contacts share the same position" —
  name the real cause: overlapping probe origins); and per-shank pitch/density is
  materialised in imported profiles (`params.per_shank` / `geometry_features`) but no
  surface renders it yet — the menu probe-UI pass consumes it.

## Definition of done (per slice)

Suite green; loader smoke green; a 30 s sort runs end-to-end with an imported probe applied
and the report's probe section rendering it faithfully (canary ~4 µV throughout — geometry
must never touch amplitude scaling); explicit-probe-fails-hard / default-falls-back-soft
asymmetry preserved; Fable review per slice.

## Boundaries and known traps

- `probes.py` stays the single owner of geometry; `blackrock_io`'s dead `attach_a1x16_*`
  path stays dead.
- Geometry still only soft-re-ranks sorters — it never blocks a sort.
- The menu's probe UI portions follow DESIGN_UX §1 language and land after D1 where they
  touch the dashboard.
- Imported probe files are user data (the gitignored `probes.json` library), never
  committed fixtures — test probes get built in-test.
