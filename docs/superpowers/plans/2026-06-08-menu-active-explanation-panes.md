# Active + Explanation Pane Dashboard — Implementation Plan

> **For agentic workers:** This plan is executed by the **Workflow** tool with a
> dedicated **audit/verify** phase (the user's chosen path), not the
> subagent-driven-development skill. Steps use checkbox (`- [ ]`) syntax for
> tracking. The authoritative design is the committed spec:
> `docs/superpowers/specs/2026-06-08-menu-active-explanation-panes-design.md` —
> tasks reference its sections rather than restating long render text.

**Goal:** Rebuild the Textual dashboard as a focus-driven two-pane view — an
**active list** (sorters *or* actions, accordion) plus a persistent **explanation
pane** — with a quiet-until-broken status line, the brain kept, and auto-advance to
actions on Enter.

**Architecture:** `scripts/menu_app.py` (Textual view) is refactored; the
`MenuController` in `SpikeInterface_Menu.py` grows action metadata
(`action_explain`) and a shared per-stream detail helper; `scripts/ui.py` keeps the
non-parity fallback. The view is a pure renderer over controller data, driven by a
new `self._mode in {"sorter","action"}` that owns focus, key-gating, and the
explanation render. Tested with Textual's `run_test`/Pilot against the
`FakeController` in `tests/conftest.py`.

**Tech Stack:** Python 3.12, Textual, rich, pytest + pytest-asyncio (`uv run python
-m pytest tests/`).

---

## File structure

- **Modify** `SpikeInterface_Menu.py` — add `_ACTION_DETAIL` + `MenuController.action_explain`; expose `controller.pipeline` (already an attribute) to the help body.
- **Modify** `scripts/ui.py` — add a shared `stream_detail(files, pipeline)` helper; pipe action `what`/`caveat` into the fallback hints (non-parity note).
- **Modify** `scripts/menu_app.py` — the accordion refactor: `#statusline`, `#activebar`, `#body` → `#activepane` (`#sorters`+`#actions`, one shown) + `#explain`; mode state + mode-switch handlers; `_render_statusline`, `_render_sorter_explain`, `_render_action_explain`; mode/status/stack-aware reserve; per-mode footers; remove `#pipeline`/`#sorterdetail`/`_render_pipeline`. Update the module-docstring ASCII.
- **Modify** `tests/conftest.py` — add `action_explain` to `FakeController`.
- **Modify** `tests/test_menu_controller.py`, `tests/test_menu_app.py`, `tests/test_fallback.py` — new + migrated tests.
- **Modify** `CLAUDE.md` — Architecture/navigation/responsive passages + fallback parity claim.

Sorter-registry `when_to_use` blurbs (spec "optional") are **out of scope** for this
plan — the explanation pane reads fine from the existing one-line `description`.

---

## Task 1: Controller — action metadata + `action_explain`

**Files:**
- Modify: `SpikeInterface_Menu.py` (after `_ACTIONS`, ~line 604; method on `MenuController`)
- Modify: `tests/conftest.py` (add `action_explain` to `FakeController`)
- Test: `tests/test_menu_controller.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_menu_controller.py`; reuse its `_controller` helper + registry monkeypatching)

```python
def _ctrl_with_two_sorters(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "mountainsort5"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    return _controller(monkeypatch, tmp_path, use_docker=False)


def test_action_explain_explore_needs_data(monkeypatch, tmp_path):
    c = _ctrl_with_two_sorters(monkeypatch, tmp_path)
    ex = c.action_explain("explore")
    assert ex["what"]                                   # has a description
    needs = {n["label"]: n["ok"] for n in ex["needs"]}
    assert any("recording" in k.lower() or "data" in k.lower() for k in needs)


def test_action_explain_compare_needs_two_saved_sorts(monkeypatch, tmp_path):
    c = _ctrl_with_two_sorters(monkeypatch, tmp_path)   # fresh tmp -> 0 saved sorts
    ex = c.action_explain("compare")
    needs = {n["label"]: n["ok"] for n in ex["needs"]}
    assert any("two" in k.lower() or "second" in k.lower() for k in needs)
    assert all(v is False for v in needs.values())      # nothing saved yet


def test_action_explain_no_need_actions_have_empty_needs(monkeypatch, tmp_path):
    c = _ctrl_with_two_sorters(monkeypatch, tmp_path)
    for key in ("params", "verify", "theme", "help", "quit"):
        ex = c.action_explain(key)
        assert ex["needs"] == [] and not ex.get("output")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_menu_controller.py -k action_explain -q`
Expected: FAIL (`AttributeError: 'MenuController' object has no attribute 'action_explain'`).

- [ ] **Step 3: Implement** — add the metadata table and method to `SpikeInterface_Menu.py`.

```python
# (module level, near _ACTIONS) Rich per-action explanation. `needs` keys are
# resolved against live state in MenuController.action_explain.
_ACTION_DETAIL = {
    "explore": {"what": "Make quick static figures (LFP traces, spike raster, "
                         "firing rates) from your raw data. No sorting required.",
                "needs": ["data"], "output": "outputs/*.png"},
    "sort":    {"what": "Detect neurons in the broadband (.ns5) signal with the "
                        "active sorter.", "choose": "full recording, or a quick 30 s test",
                "needs": ["broadband", "sort_docker"], "output": "outputs/<sorter>/"},
    "report":  {"what": "Build a single interactive HTML report of the sorted "
                        "results (run Sort first for unit results).",
                "needs": ["data"], "output": "outputs/report.html"},
    "gui":     {"what": "Open spikeinterface-gui to inspect the active sorter's "
                        "saved units.", "needs": ["saved_sort"], "output": "a desktop window"},
    "traces":  {"what": "Scroll the raw broadband traces in ephyviewer "
                        "(needs a desktop display).",
                "needs": ["broadband"], "output": "a desktop window"},
    "compare": {"what": "Build an agreement matrix between two saved sorts.",
                "needs": ["two_sorts"], "output": "outputs/comparison.html"},
    "params":  {"what": "Tune the active sorter's parameters (saved per sorter)."},
    "verify":  {"what": "Run an environment smoke test (library versions, loaders)."},
    "theme":   {"what": "Pick an accent colour for the menu (saved for next time)."},
    "help":    {"what": "What each step does, sorters, Docker, and data files."},
    "quit":    {"what": "Leave the menu."},
}

# In class MenuController:
def action_explain(self, key: str) -> dict:
    """Resolve an action's static metadata against live state into
    {what, choose?, caveat?, needs:[{label,ok}], output?}."""
    meta = _ACTION_DETAIL.get(key, {"what": key})
    info = self.infos[self.active_idx]
    present = bool(self.data_report.get("present"))
    bb = next((r for r in self.pipeline if "Broadband" in r.get("stage", "")), None)
    broadband_ok = present and (bb is None or bb.get("status") != "FAIL")
    n_saved = len(self.saved_sorters())
    resolvers = {
        "data":        ("recording files", present),
        "broadband":   ("broadband .ns5", broadband_ok),
        "saved_sort":  (f"a saved {self.active_sorter} sort", bool(info.get("present"))),
        "two_sorts":   ("two saved sorts", n_saved >= 2),
        "sort_docker": ("Docker running", not self.active_blocked_on_docker()),
    }
    needs = []
    for nkey in meta.get("needs", []):
        label, ok = resolvers[nkey]
        if nkey == "sort_docker" and not sorter_registry.uses_docker(
                self.active_sorter, self.use_docker):
            continue                                   # only relevant for a Docker sorter
        needs.append({"label": label, "ok": ok})
    out = {"what": meta["what"], "needs": needs}
    if meta.get("choose"):
        out["choose"] = meta["choose"]
    if meta.get("output"):
        out["output"] = meta["output"]
    if key == "sort" and info.get("present"):
        out["caveat"] = (f"Re-running replaces the saved {info['name']} sort "
                         f"({info['units']}u).")
    if key in ("gui",) and not info.get("present"):
        out["caveat"] = "No saved sort yet — run Sort first."
    return out
```

(Verify `sorter_registry.uses_docker(name, use_docker)` exists — it's used at
`menu_app.py` via `active_blocked_on_docker`/registry; if the signature differs,
fall back to `self.active_blocked_on_docker()` only.)

- [ ] **Step 4: Mirror on `FakeController`** (`tests/conftest.py`) so Pilot tests can call it:

```python
def action_explain(self, key: str) -> dict:
    info = self.infos[self.active_idx]
    present = self._present
    n_saved = len(self.saved_sorters())
    table = {
        "explore": ("Make quick static figures.", [("recording files", present)], "outputs/*.png"),
        "sort": ("Detect neurons in the broadband signal.", [("broadband .ns5", present)], "outputs/<sorter>/"),
        "report": ("Build an interactive HTML report.", [("recording files", present)], "outputs/report.html"),
        "gui": ("Inspect saved units.", [(f"a saved {self.active_sorter} sort", bool(info.get("present")))], "a desktop window"),
        "traces": ("Scroll raw traces.", [("broadband .ns5", present)], "a desktop window"),
        "compare": ("Agreement matrix between two sorts.", [("two saved sorts", n_saved >= 2)], "outputs/comparison.html"),
    }
    what, needs, output = table.get(key, (key, [], None))
    out = {"what": what, "needs": [{"label": l, "ok": ok} for l, ok in needs]}
    if output:
        out["output"] = output
    if key == "sort" and info.get("present"):
        out["caveat"] = f"Re-running replaces the saved {info['name']} sort ({info['units']}u)."
    return out
```

- [ ] **Step 5: Run to verify pass + no regressions**

Run: `uv run python -m pytest tests/test_menu_controller.py -q`
Expected: PASS (all, incl. existing).

- [ ] **Step 6: Commit**

```bash
git add SpikeInterface_Menu.py tests/conftest.py tests/test_menu_controller.py
git commit -m "feat(menu): action_explain — per-action needs/caveat/output metadata"
```

---

## Task 2: Shared per-stream detail helper + `d` plumbing

**Files:**
- Modify: `scripts/ui.py` (add `stream_detail`)
- Modify: `scripts/menu_app.py` (`_setup_body` consumes it; `HelpScreen` passes `controller.pipeline`)
- Test: `tests/test_data_report.py` (helper unit test)

- [ ] **Step 1: Failing test** (append to `tests/test_data_report.py`)

```python
def test_stream_detail_merges_pipeline_into_files():
    import ui
    files = [{"ext": ".ns5", "label": "Broadband — raw @ 30 kHz", "present": True}]
    pipeline = [{"stage": "Broadband (.ns5)", "status": "PASS",
                 "detail": "22 ch, 132.0s @ 30000 Hz"}]
    out = ui.stream_detail(files, pipeline)
    assert ".ns5" in out and "22 ch" in out[".ns5"] and "30000 Hz" in out[".ns5"]
```

- [ ] **Step 2: Verify failure**

Run: `uv run python -m pytest tests/test_data_report.py -k stream_detail -q` → FAIL.

- [ ] **Step 3: Implement `stream_detail` in `scripts/ui.py`**

```python
def stream_detail(files, pipeline):
    """Map each present file's ext -> the pipeline detail string (ch/rate/duration),
    matching by extension so the 'd' help (and the fallback) can show load detail
    even though the dashboard no longer renders the pipeline panel. Best-effort."""
    out = {}
    for f in files or []:
        ext = f.get("ext", "")
        row = next((r for r in (pipeline or []) if ext in r.get("stage", "")), None)
        if f.get("present") and row and row.get("detail"):
            out[ext] = row["detail"]
    return out
```

- [ ] **Step 4: Wire into `_setup_body`** (`scripts/menu_app.py`): give it the pipeline
  rows and append the detail under each present file. Change the signature to
  `_setup_body(report, accent, pipeline=None)`; in the per-file loop, after the label,
  append `ui.stream_detail(files, pipeline).get(f['ext'])` in dim when present.
  `HelpScreen._show` already has `self._c`, so pass `self._c.pipeline`:
  `body = _setup_body(self._c.data_report, self._accent, self._c.pipeline)`.

- [ ] **Step 5: Pass-through test** (append to `tests/test_menu_app.py`)

```python
async def test_data_help_shows_stream_detail(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        body = app.screen.query_one("#helpbody", Static).render().plain
        assert "30000 Hz" in body or "22 ch" in body     # per-stream detail present
```

- [ ] **Step 6: Run + commit**

Run: `uv run python -m pytest tests/test_data_report.py tests/test_menu_app.py -k "stream_detail or data_help" -q` → PASS.

```bash
git add scripts/ui.py scripts/menu_app.py tests/test_data_report.py tests/test_menu_app.py
git commit -m "feat(menu): shared stream-detail helper; 'd' help shows ch/rate/duration"
```

---

## Task 3: View — the accordion refactor (the core)

Implement spec **"Code structure → `scripts/menu_app.py`"** verbatim. This is one
cohesive change; update the affected Pilot tests in the SAME commit so the suite
stays green. Do the implementation and the test migration together.

**Files:**
- Modify: `scripts/menu_app.py` (compose tree, CSS, mode state, handlers, renders, relayout, footers, module docstring)
- Modify: `tests/test_menu_app.py` (migrations + additions below)

### Implementation steps (follow the spec section; key invariants restated)

- [ ] **Step 1 — Tree + CSS.** Compose order: `#crest`, `#titlebar`, `#statusline`
  (`height:auto`), `#activebar` (`height:1; display:none`), `#body` (`Horizontal`) →
  `#activepane` (`Vertical`: a section label + `#sorters` + `#actions`, exactly one
  `display:true`) + `#explain` (`VerticalScroll`→`Static`), `#footer`. Remove
  `#sorterdetail`, `#pipeline`, `#l-pipeline`, `_render_pipeline`. Stacked rule:
  `#body.stacked` → vertical; `#explain` gets `max-height: 40%` only when stacked.
- [ ] **Step 2 — Mode state + switch ownership.** Add `self._mode`. Add explicit
  `Binding("tab","focus_actions")` / `Binding("shift+tab","focus_sorter")` (plus
  existing left/right). `action_focus_actions`/`action_focus_sorter` MUST, in order:
  flip both lists' `display`; show/hide `#activebar`; **explicitly** re-render
  `#explain` for the now-active list; `_relayout()`; `.focus()` the now-shown list.
  Invariant (assert): exactly one of `#sorters`/`#actions` is `display:true` and is
  `app.focused`. After reveal, scroll via `self.call_after_refresh(ol.scroll_to_highlight)`.
- [ ] **Step 3 — Launch sorter mode.** `on_mount`: `self._mode="sorter"`, build both
  lists, focus `#sorters`, render the sorter explanation, `_relayout()`. (Welcome
  unchanged.)
- [ ] **Step 4 — Auto-advance.** `_select_sorter`: on a **runnable** sorter, after
  `set_active_by_name`, call `action_focus_actions()` (activate → action mode).
  Non-runnable → today's Docker-offer/hint, stay in sorter mode. `__docker__`/headers
  unchanged.
- [ ] **Step 5 — `1–9`.** `action_run_index(i)`: if `self._mode != "action"`, switch
  to action mode first (highlight row `i`, render its explanation), then activate
  action `i` — never run while invisible.
- [ ] **Step 6 — Explanation render.** Generalise `on_option_list_option_highlighted`
  to branch on `event.option_list` (`#sorters`→`_render_sorter_explain`,
  `#actions`→`_render_action_explain(self.c.action_explain(id))`). `_render_sorter_explain`
  = the multi-line full-width evolution of `_render_sorter_detail` (header states per
  spec; full description; saved/overrides; the `Press → or Enter for actions.` CTA;
  keep "no accent fg on the active name" so the chip survives the cursor wash).
  `__docker__` row → a toggle blurb; header rows → fall back to the active sorter.
- [ ] **Step 7 — Status line.** `_update_banner` → `_render_statusline(w,h)`: healthy
  → borderless `✓ Recording loaded — <verified streams>` (Events omitted/dim, never a
  banner); failure → bordered `⚠ …` (the 3 variants, reusing `data_report` +
  `controller.pipeline` broadband-`FAIL`). Return height (1/3); fold into the
  reserve. Keep the `_BANNER_MIN_ROWS` short-window suppression.
- [ ] **Step 8 — `#activebar` + footers.** Render the folded bar in action mode (forms
  per spec; never suppressed in action mode). Per-mode width-adaptive footers; the
  `→/1-9 Actions` token is last-dropped in sorter mode; both keep `? d t q`. Unify
  `t` wording.
- [ ] **Step 9 — Reserve.** `_relayout` reserve = `base + statusrows(1|3) +
  activebar(1 if action mode)`; re-fit the crest on every mode switch and quiet→loud
  transition; stacked → cap `#explain`; extreme-short wide → hide `#explain`,
  `#activepane` full width. Keep disabled action rows' inline `(needs data)` suffix.
- [ ] **Step 10 — Module docstring.** Update the layout ASCII at the top of
  `menu_app.py` to the new tree.

### Test migration (same commit) — `tests/test_menu_app.py`

- [ ] `test_boots_with_lists_and_focus` → assert `app.focused is #sorters`,
  `#sorters` displayed, `#actions.display is False`, `#sorters.highlighted ==
  _sorter_row(app,"tridesclous2")`. (`option_count` of actions still 11.)
- [ ] `test_left_right_switch_focus` → `right`/`tab` enters action mode (`#sorters`
  hidden, `#actions` shown + focused, `#activebar.display is True`); `left`/`shift+tab`
  restores sorter mode (`#sorters` shown + focused, `#activebar.display is False`).
- [ ] `test_down_moves_action_highlight`, `test_jk_navigation` → first enter action
  mode (`await pilot.press("right")`) before moving the action cursor.
- [ ] `test_enter_on_sorter_sets_active` / `test_space_selects_sorter` → after Enter,
  assert `c.active_sorter == "spykingcircus2"` AND the app is in action mode
  (`#activebar` contains `spykingcircus2`).
- [ ] Digit tests (`test_action_run_path_is_guarded`, `test_disabled_action_does_not_run`,
  `test_sort_span_modal_then_runs`, `test_sort_blocked_without_data`,
  `test_number_key_opens_param_editor`, `test_sort_modal_warns_before_overwriting`,
  `test_sort_blocked_when_active_needs_docker_thats_down`,
  `test_compare_opens_picker_when_two_saved`, `test_compare_picks_pair_and_runs`) →
  pressing the digit from the boot (sorter) state still works (auto-switches to action
  mode then runs); keep the existing assertions on `c.ran` / modal type. Where a test
  inspected `#footer` for "needs", that still holds (the disabled guard still writes
  the footer/`_last`).
- [ ] `#banner` → `#statusline` rename in `test_missing_data_shows_banner` and
  `test_unreadable_files_show_amber_banner`; keep the substring assertions ("No
  recording found", "unreadable"). Add:

```python
async def test_healthy_status_is_quiet_no_banner(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        line = app.query_one("#statusline", Static).render().plain
        assert "✓" in line and "Recording loaded" in line


async def test_active_sorter_visible_in_action_mode_bar(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")                 # -> action mode
        await pilot.pause()
        bar = app.query_one("#activebar", Static)
        assert bar.display is True and "tridesclous2" in bar.render().plain


async def test_action_explain_shows_in_action_mode(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        ex = app.query_one("#explain", Static).render().plain
        assert "figures" in ex.lower() or "explore" in ex.lower()   # row 0 = explore
```

- [ ] Keep `test_actions_stay_on_screen_when_stacked` /
  `test_missing_banner_never_clips_actions_on_tiny_windows` — but they query
  `#actions`, which is hidden in sorter mode. Update them to first enter action mode
  (`await pilot.press("right")`) so `#actions` is displayed, then assert on-screen.
- [ ] `test_tiny_window_stacks_and_keeps_actions`, `test_very_short_window_does_not_crash`,
  `test_resize_wide_to_tiny_to_wide` → enter action mode where they assert on
  `#actions`; keep the stacked/crest assertions.

- [ ] **Run + commit**

Run: `uv run python -m pytest tests/test_menu_app.py -q` → PASS.

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): focus-driven two-pane dashboard (active list + explanation pane)"
```

---

## Task 4: Fallback (ui.py) — pipe metadata, keep non-parity

**Files:**
- Modify: `scripts/ui.py` (`dashboard_menu` actions get `what` as hint; `HELP_TOPICS['data']` body via `stream_detail`)
- Modify: `SpikeInterface_Menu.py` (`_menu_fallback` passes the per-action `what`/`caveat` into the `_MENU` hints; `_print_setup_plain` uses `stream_detail`)
- Test: `tests/test_fallback.py`

- [ ] **Step 1** — In `_menu_fallback`, build the action hint list from
  `_ACTION_DETAIL[key]["what"]` (fall back to the existing `_MENU` hint), and append
  the resolved `caveat` for `sort` so the typed menu still warns before a re-sort.
- [ ] **Step 2** — `_print_setup_plain` (and `HELP_TOPICS['data']` render) use
  `ui.stream_detail(report["files"], pipeline)` to show ch/rate/duration where present.
- [ ] **Step 3 — Test** (append to `tests/test_fallback.py`): assert the fallback's
  action listing surfaces a `what` string for `sort` and the destructive caveat text
  is present when a saved sort exists. Keep it light (the fallback is intentionally
  non-parity — no accordion).
- [ ] **Step 4 — Run + commit**

Run: `uv run python -m pytest tests/test_fallback.py -q` → PASS.

```bash
git add scripts/ui.py SpikeInterface_Menu.py tests/test_fallback.py
git commit -m "feat(menu): typed fallback surfaces action descriptions + sort caveat"
```

---

## Task 5: Docs — CLAUDE.md + module docstring

**Files:** Modify `CLAUDE.md`.

- [ ] Rewrite the Architecture passages describing `#sorterdetail` (Selected-sorter
  card), the `#pipeline` panel, the responsive drop order ("pipeline first at h<22…"),
  and the navigation paragraph → document the two-pane accordion (`#statusline` /
  `#activebar` / `#explain`; sorter-mode-hides-actions; mode-switch-on-focus;
  auto-advance on Enter; `1–9` auto-switch; quiet-until-broken status; `d` carrying
  per-stream detail). Change the fallback "offers the same at parity" claim to
  "intentionally non-parity (no accordion); keeps the always-on pipeline + status
  table." (The `menu_app.py` module docstring is updated in Task 3 Step 10.)
- [ ] **Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md — two-pane accordion dashboard"
```

---

## Task 6: Audit / verify (workflow phase)

- [ ] **Full suite.** `uv run python -m pytest tests/ -q` → all green. Capture output.
- [ ] **Smoke import.** `uv run python -c "import sys; sys.path.insert(0,'scripts'); import menu_app, ui; import SpikeInterface_Menu"` → no error.
- [ ] **Adversarial diff audit.** Independent reviewers grade `git diff main...HEAD`
  against the spec's **Decisions (locked)** + per-action **needs** table +
  **Testing** list: every locked decision implemented? regressions? do the
  focus/NO_COLOR/responsive invariants hold (one displayed+focused list; loud banner
  bordered, quiet borderless; `#activebar` present in action mode; reserve
  mode/status-aware)? Report concrete gaps.
- [ ] **Remediate** any blocker/high findings, re-run the suite, re-commit.

---

## Self-review (spec coverage)

- Active+explanation accordion → **Task 3**. Launch sorter mode, actions hidden,
  auto-advance on Enter, `1–9` auto-switch → **Task 3** (steps 3–5).
- Quiet-until-broken status, Events-optional, 3 failure variants, bordered/borderless
  shape → **Task 3** step 7 + tests.
- `controller.pipeline` retained; `d` gets per-stream detail via shared helper →
  **Task 2** (+ retained implicitly: `_render_statusline` reads it).
- Per-action `needs` table (compare→two_sorts, gui→saved_sort, sort→docker-block,
  no-need actions omit footer) → **Task 1**.
- Responsive two-axis + mode/status-aware reserve, brain kept, list scrolls →
  **Task 3** steps 1, 9 + responsive tests.
- Active-vs-cursor legibility, `#activebar` vocabulary, per-mode footers → **Task 3**
  steps 6, 8.
- Fallback non-parity + metadata piping → **Task 4**. Docs → **Task 5** + Task 3 s10.
- Verification + adversarial audit → **Task 6**.

No placeholders; method names (`action_explain`, `stream_detail`,
`_render_statusline`, `_render_sorter_explain`, `_render_action_explain`,
`action_focus_actions/sorter`) and widget ids (`#statusline`, `#activebar`,
`#activepane`, `#explain`) are consistent across tasks and tests.
