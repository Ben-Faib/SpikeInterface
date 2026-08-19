# DESIGN_UX.md feasibility critique - 2026-08-18

*From the T1 session, against the real `menu_app.py` / `ui.py` / `report.py` /
`SpikeInterface_Menu.py`. Findings only, ranked by how much they change the D-track
plan; each cites the code that grounds it. Fold-in and resolution belong to the
orchestrating session before Ben's veto pass.*

## 1. §6 report/compare progress is D2's biggest unscoped lift

Report and compare run **blocking, in-process, under `suspend()`**
(`menu_app.py:2934-2943` → `controller.run()` → `DISPATCH` in
`SpikeInterface_Menu.py:1157`) - there is no subprocess, no progress channel, and
`report.py` emits nothing: all its "phases" (load analyzer, render figures, inline
Plotly, write) live inside one `build_report()` call. "Same modal pattern as sorting"
therefore means building the sort pipeline's whole plumbing a second time: a
progress-emitting CLI mode in the report path, a `report_command()` argv on the
controller (mirroring `sort_command()`), and the modal wiring. Cancel only works
cleanly with a real subprocess (the sort modal kills a process group). Recommend the
spec scope this explicitly - and consider landing it *with* D3 (report.py is being
rewritten there anyway) rather than in D2.

## 2. §3 result-card actions change the modal's return contract

"↵ close · 3 build report · 4 inspect in GUI" chains a next action out of the modal.
`SortProgressScreen` today dismisses `(ok, message, changed)`; chaining needs a new
dismissal shape (e.g. an optional `next_action`) plus app-side dispatch after the
pop - and "inspect in GUI" goes through the `_self` fresh-process path
(`QT_ACTIONS`, `SpikeInterface_Menu.py:54`), not `DISPATCH`. Feasible, but it is a
contract change the Pilot tests pin, not a cosmetic addition - put it in D2's task
list by name.

## 3. New persisted state extends a pinned contract (`.si_menu.json`)

D1's "persist active sorter" and §6's "LAST RESULT is the system's memory" both add
keys to `.si_menu.json`, whose key set is pinned in CLAUDE.md (exactly six keys,
written from ~8 call sites). The spec should decide and say: LAST RESULT in-memory
(dies with the session) or persisted; active sorter persisted (new key). Whichever -
name the new keys in the spec and update the CLAUDE.md line in the same slice, or
the "local state is exactly these keys" invariant silently rots.

## 4. §4's noise-floor "canary ✓" tile invents a pass/fail rule

The ~4 µV canary is an *observed regression signal* (3.88–4.02 across saved sorts),
not a validated threshold. A ✓/✗ stat tile turns it into a science claim - exactly
what the honesty law and the SNR≥5 lesson warn about. Define the band and its
provenance in the spec (e.g. "3.5–4.5 µV = expected for this rig, post-bandpass+CMR;
outside → amber tile with the double-scaling explanation, never red/green"), or show
the number with the expected range as text until M1 grounds thresholds properly.

## 5. The `traces` action's fate is unspecified

§2's WORKFLOW has five actions; today's menu has **traces** (ephyviewer) as a
distinct Qt action (`QT_ACTIONS = {"gui", "traces"}`), and the mock's Explore
explainer ("raw traces + events") half-implies absorption. If Explore absorbs it,
Explore becomes sometimes-a-Qt-launch (fresh `_self` process, desktop window caveat);
if it moves to MANAGE, say so. Either is fine - unstated, D1 will improvise.

## 6. §8 vs §2: the availability glyph has no in-row text neighbor

§8 commits "every glyph has a text neighbor"; the mock's sorter rows carry a bare
●/◌ column. The group headers (READY / DOCKER) are arguably the neighbor for ● but
not for the cached-vs-not distinction ◌ carries today (the current rows spell out
"⬇ get it"-style affordances - `ui.py`'s NO_COLOR-safe pattern). Pick one: a legend
line under the panel, or the word lives in INSPECTING and the spec says the group
header is the neighbor. As drawn, the mock violates its own §8.

## 7. "Both themes" (§8) doesn't exist - there is one dark palette

`ui.py`'s `THEMES` is accent colors only; `menu_app.py` CSS and inline `Text` styles
hardcode dark-background colors throughout (`#3a3f47` borders, `#3fb950` green,
`#f0883e` amber…). If "both themes" means light+dark, that's a real new capability -
a palette abstraction over ~all CSS and rich styles - not a contrast test. Either
rewrite as "all accent themes on the dark palette, contrast-tested" or scope a light
theme as its own D-slice.

## 8. §3 per-phase durations: say where the clock lives

Consumer-side arrival-time clocking needs no protocol change but can't be replayed
from a captured event log and includes pipe/startup skew; emitter-side means phase
events (or a `phase_done` event) carry the previous phase's duration. §6 says events
"gain `elapsed`" - one sentence saying *which events, measured by whom* will save D2
an improvisation. Related, cheap and safe: the phase list growing 4→5 ("Save
sorting") is an emitter constant; T1's contract tests deliberately pin neither phase
count nor titles, so no test re-baseline is needed. T1 coordination note: **extend,
don't repurpose, `done`/`error`** - the TUI synthesizes `done` from a silent rc-0
exit and its required keys are contract-pinned; a new `result` event should ride
alongside `done`, not replace it.

## 9. §5's "sane default layout" for sigui is speculative

Verify spikeinterface-gui actually supports layout persistence before the spec
promises it; nothing in our code touches it today. If it doesn't, §5's real
deliverable is just moving the flashed-past caveat into INSPECTING before launch -
worth keeping, cheap, honest.

## 10. Key/number churn is fine but must move as one commit

WORKFLOW 1–5 + MANAGE letters renumbers today's 1–6 table; `tests/conftest.py`
mirrors that table and the Pilot journeys press literal numbers, `ui.py:74`'s
fallback hint line still advertises the nonexistent `m animation` (the spec's help-
accuracy claim checks out - that string is real). D1 should name "action table +
conftest mirror + help/hint text + Pilot journeys move together" as one slice so the
suite is never half-renumbered. Dashboard-level `r` for "reopen" is free (`r` is
only bound inside modals today).
