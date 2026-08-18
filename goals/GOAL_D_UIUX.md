# GOAL D — The UI/UX overhaul: every surface accessible, focused, and timely

## Intent

Ben's 2026-08-18 directive: drastically improve the workbench's surfaces — more accessible,
less clutter, focused on what matters, clean hierarchy with ample room — and make the UX
feel like the program provides **timely updates and results**. Complete overhauls are on the
table. The design authority is `DESIGN_UX.md` (D0): its §1 design language binds every
slice, its §2–§6 specify each surface, its §7 maps spec → the slices below. The UPitt
researchers this serves get a tool that respects their attention.

## Gate

**D0 — Ben's veto pass on DESIGN_UX.md.** No D slice is built before Ben approves or amends
the spec (peer-session feasibility critique folded in first). Amendments land in the spec,
dated, then the slices run against it.

## Task (slices — one goal run each)

- **D1 — the dashboard** (spec §2): two-line banner, WORKFLOW/MANAGE split, signal-budget
  sorter rows, auto-sizing scrollable INSPECTING, LAST RESULT line, accurate help, persist
  the active sorter (update CLAUDE.md's `.si_menu.json` key list).
- **D2 — the run experience** (spec §3 §6): full-pipeline phase checklist with elapsed,
  honest progress (no 100%-while-running), translated sub-status, result cards (success /
  amber 0-unit with the detect_threshold hint / red failure with log path), protocol
  extension (`elapsed`, `phase m/n`, `result` payload), report+compare progress with cancel.
- **D3 — the report** (spec §4): verdict header + stat tiles, sticky TOC, reader-order
  sections, one chart theme + shared unit colormap, styled tables with folds.
- **D4 — flow modals** (spec §3 §1): sort-how-much expected durations, param-editor pass
  (recommended-first, overridden-vs-default marks, live validation), Manage-hub NavList
  consistency.

## Definition of done (per slice)

The suite green including T1's snapshot tests **re-baselined deliberately with the diff
reviewed** (a redesign changes snapshots by definition — the review is the point); the
30 s sort smoke green with the ~4 µV canary for anything touching the sort path; the
never-clip Pilot tests still pinning the yield order; for D2, the protocol contract tests
green with old events still valid; for D3, the rebuilt report opened and visually checked
against spec §4. Each slice gets the fresh-context Fable review before sealing.

## Boundaries and known traps

- The menu view still imports no SpikeInterface; controller Protocol boundary holds.
- `--progress json` stdout purity is untouchable; new events ride the same channel rules.
- NO_COLOR/mono-font safety and the responsive yield order are law (spec §1.5, §8).
- Esc stays a no-op on the dashboard; destructive ops keep their confirm modals.
- spikeinterface-gui is upstream — stance per spec §5, no forking for looks.
- Don't start curation features (W1) or versioned runs (W2) from inside D slices — where a
  D surface wants them (result history, run provenance), it shows what exists today and
  leaves the seam.
