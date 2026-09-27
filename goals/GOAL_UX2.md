# GOAL UX2 - The usability pass: true words, finished loops, one meaning per key

## Intent

The surfaces are built (D1-D6, face1/face2, the presentation facelift). What is left is
the friction a researcher hits using them: words that are no longer true, a curation loop
that ends by telling you to leave the app, keys that mean three things, and HTML pages
that each look and read differently. UX2 polishes what exists. It does not pick the W3
face and grows no new surface. DESIGN_UX.md §1 binds every slice. The job is confidence:
every function does what its row says, and we can show it.

Sources: a code-checked sweep of every recorded follow-up (2026-09-27, 24 still open), plus
a look at every surface (dashboard, triage, sort modal, report, sweep, comparison).

## Slices (one goal run each, in this order; Ben picks which run)

**UX2-0 - the confidence harness (first, because every later slice is judged by it).**
Add one command that drives all fourteen dashboard functions headlessly against the real
recording. Each gets a pass/fail line: loaded / sorted (30 s, canary) / labelled / applied /
report built with the curated state stated / compare built / export-phy written / sigui
opens in web mode. Then run it before and after every UX2 slice. The Pilot suite fakes the
controller, and verify-spike covers the sort alone, so today no single check proves the
fourteen rows work end to end. Size M.

**UX2-A - say only true things (correctness of what surfaces tell the researcher).**
- Report names the menu's CURRENT probe, not the one the sort used: the menu always passes
  `--probe <active>` and report.py lets the flag win (SpikeInterface_Menu.py:1495,
  report.py:2101). S
- `report`/`gui` actions show the "placeholder independent probe" caveat on real-geometry
  sorts: they read run_info `probe` (None on flagless sorts) instead of `probe_id`
  (SpikeInterface_Menu.py:519, :674). S
- "Sort how much?" warns a re-sort "replaces" the saved sort, but since W2 every run is
  kept (menu_app.py:3914). S
- Clear-saved-sort confirm says "you can re-run later" but deletes every run, the
  curation and Phy exports: name the count (menu_app.py:1629). S
- Triage's empty state says "No saved sort - press 2" when only metrics are missing
  (SpikeInterface_Menu.py:1271). S
- Phy: re-import hint drops `--from <dir>`; exit 0 when every verdict is rejected
  (curation.py:1564, :1645). S
- Narrow terminals crop the state block mid-word ("Ready to", "NeuroNexus"): truncate
  with an ellipsis at a field boundary (test_dashboard_narrow_stacked snapshot). S
- Quiet/non-TTY sort output truncates every metrics column to "1.…": print fewer columns
  or wrap. S
- Report table headers have a dead click zone around the sort button (report.py:648). S
- Probe import error "two contacts share the same position" should say overlapping
  shank origins (probes.py:353). S

**UX2-B - finish curation inside the app.**
- Triage ends with "run `uv run python scripts/curation.py apply`": add an in-TUI apply
  (with its progress + result card, same subprocess pattern as sort). M
- Judge with evidence, not only numbers: a waveform sparkline + ISI mini-histogram in the
  unit pane (Unicode blocks, NO_COLOR-safe), and order units advised/unjudged first. M
- The quality rule is read from `.si_menu.json` but no UI writes it: a small editor (with
  the rule's current pass count live). M
- Phy export hardening: stale seeded labels re-import as "phy" verdicts; raw exports seed
  labels without an anchor check (curation.py:1525, W1 F4/F5). M
- Record hardening: corrupt record treated as absent and overwritten; triage check-then-
  write race; `_TRIAGE_KEYS` unpinned against `QUALITY_OPTIONS`. S each

**UX2-C - one meaning per key.** `c` = colour (dashboard) / collapse (downloads) / clear
saved sort (manage, destructive); `g`, `x`, `r`, `e` are each overloaded three ways across
screens; `u`/`m` mean triage/manage outside triage and unsure/MUA inside it. Build one key
table (help renders it, a test pins it), rename the destructive and colliding ones,
keep the dashboard's 1-6 meanings (decision of record). Snapshots re-baselined
deliberately. S-M

**UX2-D - timeliness gaps.** An amber "no output for 90 s - still running" note on long
quiet sorter phases (DESIGN_UX §6); a live timer on the running phase row; a full run
whose metrics crashed should not take the current pointer from a complete run
(runs.py:489). S-M

**UX2-E - the HTML pages as one site.**
- When a curation exists, the report leads with the human verdicts (the 4 good units that
  recover the manual sort at 97.5-100%); today it leads with "no unit passes on solid
  evidence" and a table topped by 26-57-spike units.
- Dense explanatory paragraphs (the advisory, the manual column) go behind folds; the
  verdict stays one screen.
- comparison.html gets a verdict headline like sweep.html, flags legacy runs and mixed
  windows (20 s legacy sorts sit beside 132 s ones), and drops "Self-contained - works
  offline" as its subtitle.
- A shared header links report, comparison, sweep and explore.
- Close the §4/§8 audit (figure alt text, table folds) line by line. M

## Deferred - Ben's calls, not in UX2

Light theme (DESIGN_UX §8, "only if Ben wants it"; 99 hardcoded hex colours make it L) ·
decisions made in sigui are lost + no curated sigui layout (M-L) · per-shank pitch display
(waits on a multi-shank lab probe) · GPU sorters + the lab box (WD) · the W3 face pick.

## Gates (every slice)

verify-spike's table: the full suite (snapshots re-baselined only deliberately, diff
reviewed), the 30 s sort smoke with the ~4 µV canary where sort-adjacent, build + open
each touched HTML page, a real launch for anything Pilot cannot see, and UX2-0's harness
green before and after. One Fable review per slice before sealing. NO EM DASHES.
