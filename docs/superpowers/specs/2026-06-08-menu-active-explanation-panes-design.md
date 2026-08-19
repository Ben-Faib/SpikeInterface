# Dashboard: active pane + explanation pane (focus-driven) - design

**Date:** 2026-06-08
**Topic:** Restructure the Textual dashboard (`scripts/menu_app.py`) around two
panes - a focus-driven **active list** (sorters *or* actions) and a persistent
**explanation pane** that describes the highlighted row - replacing the cramped
38-col sidebar (list + selected-sorter card + pipeline). Load status becomes a
quiet one-liner that turns into a loud banner only on failure. The brain crest is
kept (large on tall windows; it still collapses on short ones).

> This spec was hardened against a 5-lens adversarial review (UX, Textual
> feasibility, responsive budget, accessibility/NO_COLOR, tests/fallback/scope).
> Findings are folded in below; the few that touched the user's locked choices are
> called out in **Open question** at the end.

## Problem

The current dashboard puts the four things the user cares about
(*which sorter*, *info about the sorter*, *the actions*, *did it load*) into a
narrow 38-col left column stacked under a tall crest, while the right Actions pane
is ~60 cols and half-empty. Consequences observed on screen:

- **Horizontal imbalance → truncation.** Sorter description ("Fast, reliable,
  CPU-only. Good d…"), pipeline detail ("22 ch, 132.0s @…"), and the selected card
  are all cut with `…` because the densest content sits in the narrowest column.
- **Active vs. cursor ambiguity.** When the cursor rests on the active sorter row,
  the `ACTIVE` chip and the cursor highlight overlap and look identical; and the
  "Selected sorter" card shows the *highlighted* sorter, which silently disagrees
  with the active one when you scroll.
- **Load status is buried.** The `PIPELINE` box is the lowest, narrowest thing on
  screen and its detail is unreadable; a failure is just a red row, not loud.

## The model

Exactly two panes are on screen at any time:

- **Active pane** (left) - the list you are currently navigating. It holds the
  **sorter catalog** in *sorter mode* and the **actions list** in *action mode*.
  Only one list is expanded at a time (accordion); the other is folded away.
- **Explanation pane** (right) - always describes the row the cursor is on: a
  sorter's blurb in sorter mode, an action's rich blurb in action mode.

Switching focus switches mode. Entering action mode folds the sorter list into a
single `▸ Active sorter: …` bar so you never lose track of what actions run on;
returning to sorter mode unfolds it. Load status is a quiet one-line summary that
expands into a loud bordered banner the moment a stream fails to load.

## Decisions (locked)

- **Two panes, focus-driven accordion.** Active pane content swaps sorters↔actions
  with focus; the non-focused list collapses. Explanation pane is always present and
  always reflects the highlighted row.
- **Launch in sorter mode.** First frame: sorter list expanded + its explanation;
  the actions list hidden. (User: "sorters first.")
- **Sorter mode hides the actions *list*** - but the workflow is **not** invisible:
  the bridge to actions is advertised three ways (see *Discoverability* below). The
  full actions list is one keypress away (`→` / `Tab` / `1–9`).
- **Action mode folds the sorter list** to one line:
  `▸ Active sorter: ★ <name> · <saved>   ← to change` (forms below).
- **Explanation pane is rich**, especially for actions: *what it does · what you'll
  choose · ⚠ caveats · a compact Needs / Output footer* - with `needs` resolved
  against live state (per-action table below).
- **Load status: quiet-until-broken.** Healthy → one borderless dim line with a
  leading `✓`. Any failure → a **bordered** banner (the border + leading `⚠` are the
  shape cues, so quiet/loud are distinguishable under NO_COLOR) naming the exact
  problem + remedy (`d` help · `f` folder). The standalone **`#pipeline` widget is
  removed from the main view**; its per-stream detail (channels/rate/duration) is
  relocated to the `d` **Data files** help - see the mandatory plumbing in *Code
  structure*. **`controller.pipeline` (the data) is retained**: it still feeds the
  status line's unreadable-broadband detection and the `d` detail.
- **Brain crest kept** - large on tall windows (the screenshot's 41+ row case),
  still yielding full→compact→mini→hidden on shorter windows via the existing
  ladder. "Kept" means *not replaced by a wordmark*; it is not exempt from
  collapsing when rows are scarce. The sorter catalog (~27 rows) **scrolls** when it
  doesn't fit - `scroll_to_highlight` keeps the active/cursor row visible. (The
  accordion's win is that the explanation pane is always present *without a third
  stacked panel*; it does not make the whole catalog fit under a full brain.)
- **Enter on a runnable sorter activates it *and auto-advances to action mode*** -
  the choose→run flow is one motion, and itself the strongest discoverability cue
  (the user lands *in* the actions list immediately). The folded `#activebar`
  confirms the now-active sorter. Enter on a **non-runnable** sorter does **not**
  advance - it stays in sorter mode (offers to enable Docker / shows the block hint,
  today's behavior); Enter on the **Docker toggle row** flips it (no advance). `t`
  cycles the active runnable sorter from either mode.
- **`1–9` jump-run an action from either mode.** From sorter mode a digit **first
  switches to action mode** (revealing the actions list + `#activebar` + the action
  explanation) **then** runs action *i* - so an action is never run while invisible
  (destructive sorts still gate on their confirm modal).
- **Global keys work in both modes:** `d f t q ? 1–9` and `←/→`/`Tab` are global;
  only `↑/↓`/`j`/`k`/`Enter` are local to the focused list.

### Discoverability (mitigations for "actions hidden at launch")

The review flagged the biggest UX risk: a newcomer landing on a list of algorithm
names with no visible verb. We keep "sorters first / actions list hidden" but make
the bridge unmissable:

0. **Enter auto-advances** to the actions list (see Decisions). The most common path
   - pick a sorter, press Enter - lands the user *in* the actions, so the verbs
   appear by doing the obvious thing. This is the primary mitigation.
1. The **sorter explanation** ends with a call-to-action `Press → or Enter for
   actions.`, for users who browse the catalog without activating.
2. The **footer** in sorter mode leads with the bridge and never drops it on
   truncation: `→ / 1-9  Actions` is the *last* token removed at narrow widths.
3. *(Optional, belt-and-suspenders.)* A **one-time first-run tip** gated on a new
   `seen_actions_hint` flag in `.si_menu.json`, shown until the user enters action
   mode once. Likely unnecessary given (0); include only if cheap.

## Layout

### State A - sorter mode (launch state)

```
                 ( brain crest - large on tall windows )
        ─────────── University of Pittsburgh · SpikeInterface ───────────
   ✓ Recording loaded - LFP · Broadband · .nev          (quiet; Events optional)

   ┌ SORTERS ───────────────────────────┐  ┌ tridesclous2   ★ · ACTIVE ────────────┐
   │ [x] Docker sorters: on             │  │ Ready to run · CPU-only · no Docker    │
   │ READY TO USE                       │  │                                        │
   │   lupin             -              │  │ Fast, reliable template-matching       │
   │   simple            2u             │  │ sorter. The safe default when you have │
   │ ▌ ★ tridesclous2    13u   ACTIVE   │  │ no GPU. Detects well-isolated units.   │
   │   spykingcircus2    8u             │  │                                        │
   │ DOCKER SORTERS (heavier)           │  │ Too few / too many? Edit the sorter    │
   │   combinato         -              │  │ parameters (Edit sorter parameters).   │
   │   hdsort            -              │  │                                        │
   │   ...                              │  │ Saved sort    13 units · 12 s          │
   │                                    │  │ Custom params none                     │
   │                                    │  │ Press → or Enter for actions.          │
   └────────────────────────────────────┘  └────────────────────────────────────────┘
   ↑/↓ choose · Enter activate · →/1-9 Actions · t switch · d data · ? help · q quit
```

Explanation-header states (text-first, so they survive NO_COLOR):
- **active** sorter → `<name>   ★ · ACTIVE` (seen when you return to sorter mode
  with `←`; Enter auto-advances rather than dwelling here).
- **non-active** runnable → `<name>  ·  press Enter to make active`.
- **non-runnable** → *leads* with the block reason
  (`Runs via Docker (~1 GB)` / `Needs an NVIDIA GPU` / `Not installed here`) + how
  to enable (e.g. "turn on Docker sorters at the top of the list").
- cursor on the **Docker toggle row** (`__docker__`) → a short blurb explaining the
  toggle. cursor on a **group header** (disabled, fires no highlight event) → the
  pane keeps showing the active sorter (reuse `_highlighted_info`'s fallback).

### State B - action mode (sorter list folded)

```
                 ( brain crest - large on tall windows )
        ─────────── University of Pittsburgh · SpikeInterface ───────────
   ✓ Recording loaded - LFP · Broadband · .nev

   ▸ Active sorter:  ★ tridesclous2 · 13 units · 12 s saved          ← to change

   ┌ ACTIONS ───────────────────────────┐  ┌ Run / re-run sorting ──────────────────┐
   │ 1  Explore raw data                │  │ Detect neurons in the broadband signal │
   │ 2  Run / re-run sorting       ◀    │  │ using tridesclous2.                    │
   │ 3  Build & open report             │  │                                        │
   │ 4  Open GUI inspector              │  │ You'll choose: full recording, or a    │
   │ 5  Scroll raw traces               │  │ quick 30 s test.                       │
   │ 6  Compare sorters                 │  │                                        │
   │ 7  Edit sorter parameters          │  │ ⚠ Re-running replaces the saved        │
   │ 8  Verify install                  │  │   tridesclous2 sort (13u).             │
   │ 9  Change colour theme             │  │                                        │
   │    Help                            │  │ Needs   broadband .ns5  ✓              │
   │    Quit                            │  │ Output  outputs/tridesclous2/          │
   └────────────────────────────────────┘  └────────────────────────────────────────┘
   ↑/↓ choose · Enter run · 1-9 jump · ← Sorters · t switch · d data · ? help · q quit
```

**Folded `#activebar` forms** (reuses the `★` + name + units vocabulary; it
intentionally drops the `▌` bar + reverse `ACTIVE` chip because it is the *sole*
sorter on screen, so "active" is unambiguous):
- saved sort present → `▸ Active sorter: ★ tridesclous2 · 13 units · 12 s saved   ← to change`
- no saved sort → `▸ Active sorter: ★ tridesclous2 · not sorted yet   ← to change`
- active sorter non-runnable (only when nothing is runnable) → append `· needs Docker` / `· needs a GPU` / `· not installed`.

`#activebar` is **never suppressed while in action mode** - it is the mode's shape
cue (its presence/absence distinguishes the two modes when both show a single
`OptionList`). It ranks above the explanation pane and brain in the responsive
floor.

### Load failure (replaces the quiet line, bordered)

```
   ┌ ⚠ PROBLEM LOADING YOUR RECORDING ──────────────────────────────────────────────┐
   │ ✗ Broadband (.ns5) is missing - it's the stream spike sorting needs.            │
   │   Explore and LFP still work.   Press  d  for setup help  ·  f  to pick folder. │
   └─────────────────────────────────────────────────────────────────────────────────┘
```

Three failure messages, reusing today's detection: **missing** (no set found),
**incomplete** (set present, some files missing - name them), **unreadable**
(complete set but the broadband `pipeline` row is `FAIL`). **Empty Events is NOT a
failure** - `read_events` is best-effort and returns `[]` with no error, so the
quiet healthy line lists only verified streams (`LFP · Broadband · .nev`) and never
escalates to a banner for missing markers.

### Responsive (two-axis - the key correction from review)

Side-by-side `#activepane` and `#explain` are co-equal height (both `1fr` inside a
`Horizontal`), so shrinking `#explain` frees **no** rows for the list. The rules
therefore differ by axis:

- **Wide (`width ≥ NARROW_COLS=78`, side-by-side).** The active list and explanation
  are co-equal; to protect the active list, the **chrome above** yields, in order:
  brain (full→compact→mini→hidden), then - only on extreme shortness - `#explain` is
  hidden (`display:false`) and `#activepane` expands to full width. The active list
  itself is an `OptionList` and **scrolls** rather than clips.
- **Narrow (`width < NARROW_COLS`, stacked).** `#body` stacks: active pane on top,
  `#explain` below with `max-height: 40%` so the active pane keeps the majority
  (mirrors today's `#sidebar { max-height: 50% }` trick, inverted to favour the
  list). Here "shrink `#explain` before dropping it" actually works.

**Brain reserve is mode- and status-aware.** Generalise today's
`reserve = SHIELD_RESERVE + (3 if banner_on else 0)`:
`reserve = base + statusrows + activebarrows`, where `statusrows = 1` (quiet) or `3`
(loud, +2 over quiet), `activebarrows = 1` in action mode else `0`. `fit()` is
re-run on every mode switch and on the quiet→loud transition so the brain yields a
tier rather than the active list losing rows. Keep the existing `_BANNER_MIN_ROWS`
suppression so a loud banner never pushes the body off a very short window.
Approx. resulting brain tiers (full=14 / compact=9 / mini=6 rows): full at
height ≳ 40, compact ≳ 34, mini ≳ 30, hidden below - biased one tier larger than
today when rows allow, with list-scroll as the accepted overflow.

## Code structure

### `scripts/menu_app.py` (the bulk of the change)

- **Widget tree.** Replace `#sidebar` (`SORTER` label + `#sorters` + `#sorterdetail`
  + `PIPELINE` + `#pipeline`) and `#mainpane` (`ACTIONS` + `#actions`) with, in
  compose order: `#crest`, `#titlebar`, **`#statusline`** (Static; quiet line or
  loud bordered banner), **`#activebar`** (Static; the action-mode fold, `display:
  none` except action mode), **`#body`** (`Horizontal`) → **`#activepane`**
  (`Vertical`: a section label + **both** `#sorters` and `#actions` OptionLists,
  only the mode's list `display:true`) + **`#explain`** (`VerticalScroll` → Static),
  `#footer`. CSS: `#statusline { height: auto }` (1 row quiet, grows to the 3-row
  bordered banner); `#activebar { height: 1; display: none }`; `#explain` capped at
  `max-height: 40%` only in the stacked state.
- **Mode state + the mode switch owns everything.** `self._mode in {"sorter",
  "action"}`. Add explicit bindings `Binding("tab", "focus_actions")` /
  `Binding("shift+tab", "focus_sorter")` (Tab can't traverse to a `display:none`
  list otherwise). `action_focus_actions` / `action_focus_sorter` are the single
  mode-switch entry points and must, in order: (1) flip both lists' `display`; (2)
  show/hide `#activebar`; (3) **explicitly re-render `#explain`** for the now-active
  list (revealing a list fires *no* `OptionHighlighted`, so do not rely on the
  event); (4) `_relayout()` (so the brain reserve re-fits for the new mode); (5)
  `.focus()` the now-displayed list - **never leave focus on the just-hidden list**
  (a hidden `OptionList` stays `focusable` and keeps eating keys). Invariant
  (assert + test): exactly one of `#sorters`/`#actions` is `display:true` and is the
  focused widget. After revealing a list, scroll via
  `self.call_after_refresh(ol.scroll_to_highlight)` (a just-revealed widget has no
  laid-out lines yet), keeping the existing try/except.
- **`action_run_index` (1–9)** switches to action mode if needed (highlight row `i`,
  render its explanation) **then** activates action `i`, so nothing runs invisibly.
- **Explanation rendering.** Generalise `on_option_list_option_highlighted` to
  branch on `event.option_list`: `#sorters` → `_render_sorter_explain(info)`;
  `#actions` → `_render_action_explain(meta)`.
  - `_render_sorter_explain(info)` - multi-line, full-width evolution of today's
    `_render_sorter_detail`: header (name + `★`/`ACTIVE`/"press Enter…"/block
    reason), full (un-truncated) description, when-to-use/tuning hint (generic when
    the optional registry blurb is absent - no brittle action-index references),
    `Saved sort` + `Custom params` lines, and the `→ for actions` CTA. The active
    row's `▌` bar + reverse `ACTIVE` chip must stay legible **under** the focused
    cursor wash - keep the existing rule (no accent fg on the name).
  - `_render_action_explain(meta)` - from the controller's resolved action metadata:
    *what* paragraph, optional *you'll choose* line, optional `⚠` caveat, and a
    `Needs … ✓/✗` + `Output …` footer (omitted entirely for needs-nothing actions).
- **Status line.** Generalise `_update_banner` → `_render_statusline(w, h)`: healthy
  → a borderless quiet line (leading `✓`, verified streams only); failure → the
  bordered banner (leading `⚠`). Reuse the `data_report` + `controller.pipeline`
  broadband-`FAIL` detection. Report its height (1/3) up to `_relayout` for the
  reserve.
- **Remove** the `#pipeline` / `#l-pipeline` widgets and `_render_pipeline`; keep
  `controller.pipeline` as data. Drop the old `#sorterdetail`/pipeline relayout
  show/hide; add the mode/stack/`#activebar`/`#explain`-drop rules above.
- **Launch.** `on_mount`: `self._mode = "sorter"`, build both lists, focus
  `#sorters`, render the sorter explanation, `_relayout()`. Welcome screen unchanged;
  add the one-time `seen_actions_hint` cue.
- **Disabled action rows** keep the inline `(needs data)` suffix (today's line) as a
  width-independent fallback, so the "why disabled" reason never depends on
  `#explain` being on screen.

### `SpikeInterface_Menu.py` (controller + action metadata)

- **Action metadata** - extend `_ACTIONS` (or a parallel `_ACTION_DETAIL`) with
  `what` (1–2 sentences), `choose` (optional), `caveat` (optional, may reference
  live state), `needs` (list of requirement keys), `output` (path/result, optional).
  Add `MenuController.action_explain(key) -> dict` that resolves `needs` to `✓/✗`
  and fills the dynamic caveat against **live state**. Resolution per action:

  | action | needs (evaluator) | dynamic caveat / note | output |
  |---|---|---|---|
  | explore | `data` (`data_report.present`) | - | `outputs/*.png` |
  | sort | `broadband` (present **and** pipeline broadband ≠ FAIL); plus docker-block via `active_blocked_on_docker()` for a Docker active sorter | "replaces the saved `<sorter>` sort (Nu)" *only when* `info.present`; else no caveat | `outputs/<sorter>/` |
  | report | `data` (best with a saved sort - note "run Sort first for unit results") | - | `outputs/report.html` |
  | gui | `saved_sort` (active sorter `info.present`) | "no saved sort - run Sort first" when absent | opens spikeinterface-gui |
  | traces | `broadband`; note "needs a desktop display" | - | opens ephyviewer |
  | compare | `two_sorts` (`len(saved_sorters()) ≥ 2`) | "need a second saved sort" when `< 2` | `outputs/comparison.html` |
  | params, verify, theme, help, quit | none | - | omit the Needs/Output footer |

  `action_explain` reads existing controller methods (`data_report`, `infos`,
  `saved_sorters`, `active_blocked_on_docker`) - no new state needed.
- **`d` Data-files detail (mandatory plumbing).** The per-stream channels/rate/
  duration live **only** in `controller.pipeline` rows (built by `report._gather`),
  *not* in `data_report` (which carries only `{ext,label,present}`). So `_setup_body`
  must additionally receive `controller.pipeline` and render a detail line under
  each present file (e.g. `✓ …ns5  Broadband - raw @ 30 kHz (sortable)   22 ch ·
  132.0 s @ 30000 Hz`). Provide this via a **shared helper** so the same per-stream
  detail can feed both `_setup_body` (Textual `d`) and the fallback's
  `HELP_TOPICS["data"]` body. `HelpScreen` already takes the controller, so it can
  read `controller.pipeline`.

### `scripts/sorters.py` (optional, nice-to-have)

- Optional richer per-sorter blurb (`when_to_use` / longer description), falling back
  to today's one-line `description(name)`. The explanation pane reads fine without it
  (description + group reason + saved summary + overrides). Defer if it bloats the
  change; the State-A tuning sentence stays generic so the mock matches the no-map
  fallback.

### `scripts/ui.py` (fallback - honest, non-parity)

The typed / prompt_toolkit `dashboard_menu` **intentionally does NOT get the
accordion or the explanation pane**: it keeps today's always-visible Sorters +
Pipeline + Actions and the always-on `status_table` (it has no horizontal pressure,
so keeping detail is a feature, not a regression). Wire the new action `what` text -
and the destructive-`sort` `caveat` - into the fallback action `hint` so it still
warns before a re-sort. The `d`/Data-files per-stream detail uses the shared helper
above so the channels/rate/duration read identically across both front-ends. The
`_MENU` vs `_ACTIONS` tables stay separate; note this divergence explicitly rather
than implying layout parity.

## Behavior / edge cases

- **Activation & auto-advance:** Enter on a runnable sorter activates it **and**
  switches to action mode (`action_focus_actions`: focus → `#actions`, `#activebar`
  shows the now-active sorter, `#explain` shows the highlighted action). Enter on a
  non-runnable sorter does **not** advance (stays in sorter mode; Docker offer /
  block hint). Enter on the Docker toggle flips it (no advance). `1–9` likewise
  switch to action mode before running.
- **Non-runnable active sorter** (only when nothing is runnable): `#activebar`
  appends the block reason; action explanations still resolve their own `needs`
  (e.g. `sort` shows the docker-block).
- **No saved sort anywhere** (fresh clone): `#activebar` shows "not sorted yet";
  `sort` drops its replace caveat; `gui`/`report` show `Needs saved sort ✗ - run
  Sort first`; `compare` shows `Needs two saved sorts ✗`.
- **Missing data:** data-needing actions stay dimmed/disabled with the inline
  `(needs data)` suffix; their `#explain` shows the unmet need in red; loud banner on
  top.
- **Docker toggle row** stays pinned atop the sorter list (sorter mode); its
  `#explain` describes the toggle.

## Testing

Replace the vague "update the tests" bullet with an explicit migration + additions
(`tests/test_menu_app.py`):

- **Boot-state flips** - `test_boots_with_lists_and_focus`: now
  `app.focused is #sorters`, `#actions.display is False`, `#sorters.highlighted ==`
  active row, `#explain` contains the active sorter's blurb. `option_count` of
  actions still 11 (options aren't cleared, just hidden).
- **Focus/mode** - `test_left_right_switch_focus` and any `tab` test: assert
  `→`/`Tab` enters action mode (`#sorters` hidden, `#activebar` visible naming the
  active sorter, `#actions` visible + focused, `#explain` shows the action), and
  `←`/`Shift-Tab` restores sorter mode; assert `app.focused` is always the displayed
  list.
- **Enter / auto-advance** - Enter on a runnable sorter activates it AND enters
  action mode (`#actions` focused, `#activebar` names it); Enter on a non-runnable
  sorter stays in sorter mode (Docker offer / hint, no advance).
- **Digit keys** - `test_action_run_path_is_guarded`, `test_disabled_action_does_not_run`,
  `test_sort_blocked_without_data`, `test_number_key_opens_param_editor`: pressing a
  digit from sorter mode switches to action mode first, then runs/guards.
- **Status line** - rename `#banner` → `#statusline`; update copy assertions; quiet
  line for a complete/readable set (incl. **zero events**); the three loud variants
  (missing / incomplete / unreadable-broadband - keep the `pipeline[1].status='FAIL'`
  exercise); assert the loud state has a border and the quiet state does not
  (NO_COLOR shape check).
- **Explanation correctness** - non-runnable sorter shows the block reason;
  `compare` shows `Needs two saved sorts ✗` with `<2` saved; `sort` shows the
  docker-block when the active sorter is a Docker sorter with Docker down; a
  needs-nothing action omits the Needs/Output footer.
- **`d` detail** - the Data-files body contains the channel/rate/duration string for
  a present stream.
- **Responsive** - at a small/narrow size (e.g. 30×70) the active list keeps a floor
  of visible rows, panes stack with `#explain` capped, and `#activebar` is present in
  action mode.

## Docs

- **CLAUDE.md** - rewrite the Architecture passages describing `#sorterdetail`
  (Selected-sorter card), the `#pipeline` panel, the responsive drop order
  ("pipeline first at h<22, then the Selected-sorter card at h<20"), and the
  navigation paragraph; document the two-pane accordion (`#statusline` /
  `#activebar` / `#explain`, sorter-mode-hides-actions, mode-switch-on-focus,
  `1–9` auto-switch, quiet-until-broken status, the `d` topic now carrying
  per-stream detail). Update the fallback "offers the same at parity" claim to
  "non-parity (no accordion); keeps the always-on pipeline + status table."
- **`scripts/menu_app.py` module docstring** (the layout ASCII at the top) - update
  to the new tree.

## Out of scope

- The brain crest art and its ladder (kept as-is).
- The Qt GUIs, report/compare internals, the sorter registry's set of sorters.
- The theme palette.
- Re-theming the fallback typed menu (intentionally non-parity).

## Resolved during review

- **Discoverability fork → auto-advance on Enter.** Rather than a persistent actions
  hint strip (which would soften "fully hidden"), Enter on a runnable sorter now
  auto-advances into action mode (Decisions + Discoverability §0). This keeps the
  actions list hidden at rest while making the verbs appear on the most common
  action. No persistent strip.
