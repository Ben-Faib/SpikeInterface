# GOAL W0 — Quick wins: retire the audit's dead-ends before any path work

## Intent

The 2026-06-27 audit (WORKBENCH_DIRECTIONS.md, "Quick wins worth doing regardless of path")
named seven small fixes that remove the workbench's worst dead-ends without committing to any
direction. Two have since landed (Explore now opens its figures, 7940f96; sort stderr now goes
to a per-run log, `4807ce0`-era work). Five remain, verified against source 2026-08-18. They
are the cheapest trust the tool can buy, and the last one — widening the metric suite — is the
explicit precondition for W1 and for every later path's signature feature.

## Task (the five remaining wins)

1. **Kill the false-green 0-unit success.** `SortProgressScreen.action_close_if_done`
   (`scripts/menu_app.py:722`) builds its own `✓ Sorted {units} units`, so a 0-unit sort shows
   green and the genuinely useful hint — `⚠ no units found — lower detect_threshold (Edit
   parameters) and re-run` (`SpikeInterface_Menu.py:294`) — never reaches the in-UI flow.
   Route the in-UI done event through the same message/severity logic so 0 units reads as an
   amber result carrying the fix.
2. **Make the INSPECTING panel readable.** `#inspect` is `max-height: 7`
   (`scripts/menu_app.py:1729`) and non-focusable (`:1799`), while `_render_sorter_explain`
   writes ~10–12 lines — the description tail and the CTA are silently clipped. Let it scroll
   or guarantee the content fits; either way nothing is silently cut.
3. **Persist the active sorter.** `.si_menu.json` saves `active_probe` but not the active
   sorter, which resets to the recommended default every launch
   (`SpikeInterface_Menu.py:763`). Persist it the same way `active_probe` is persisted
   (note: the config-key list in CLAUDE.md "Conventions" must be updated to match).
4. **Fix the keyboard help.** `ui.py:74` advertises an `m animation` binding that doesn't
   exist and the help/footer omit the real `x` (manage highlighted sorter) and `w`
   (re-expand download) bindings. Correct the text; make x/w discoverable.
5. **Widen the computed quality metrics.** `scripts/run_sorting.py:1054` hardcodes
   `["firing_rate", "snr", "isi_violation"]` while `principal_components` is already computed
   and discarded. Add presence_ratio, amplitude_cutoff/amplitude_median, and the cheap
   PCA-based isolation metrics (isolation_distance, l_ratio, d_prime, nn_hit_rate). The
   report's metrics table shows what the analyzer has — confirm it degrades gracefully for
   old saved analyzers that lack the new columns.

## Definition of done

Suite green (`uv run python -m pytest tests/`); sort smoke green
(`uv run python scripts/run_sorting.py --duration 30 --probe nnx-a1x16-3mm-100`) with the
noise-floor canary at ~4 µV; a deliberate 0-unit sort (crank `detect_threshold` up) shows the
amber hint in the UI (Pilot or real launch); the INSPECTING panel shows its full content;
relaunching the menu restores the previously active sorter; the help names only real
bindings; the new metric columns appear in the saved analyzer and the report renders them.
Fresh-context Fable review of the diff before sealing.

## Boundaries and known traps

- Each fix at its stated scope — no adjacent refactors, no curation features (that's W1).
- The µV double-scaling gate and the aux-drop ordering are untouchable (CLAUDE.md invariants).
- `--progress json` stdout purity: any new sort-path output goes to stderr in that mode.
- Widening metrics must not make metrics fatal: the Sorting saves before metrics run, and a
  metrics crash degrades to success-with-note — preserve that, including the cleanup of
  half-built derived files.
- The SNR≥5 "high-quality" headline rule stays as-is for now — replacing it with defensible
  thresholds is W1's job; don't half-do it here.
