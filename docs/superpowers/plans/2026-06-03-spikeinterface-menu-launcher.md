# SpikeInterface_Menu Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single root-level launcher (`SpikeInterface_Menu.py`) that fronts every workspace capability - explore, sort, report, GUI inspector, trace browser, sorter comparison, verify - and make the HTML report sorter-aware.

**Architecture:** A root launcher with a status dashboard + numbered menu (CLI-shy friendly) and direct arg-dispatch (power users). It shells out to the existing `scripts/*.py` for explore/sort/verify, calls `report.build_report(...)` in-process, and launches the blocking Qt GUIs (`sigui`, `ephyviewer`) in fresh child processes. A new `scripts/compare.py` builds a standalone `outputs/comparison.html`. `scripts/make_report.py` shrinks to a thin shim.

**Tech Stack:** Python 3.12, conda env `si_env`, SpikeInterface 0.104.3, spikeinterface-gui 0.13.1 (`sigui`), ephyviewer 1.8.0, Plotly, PyQt5. No pytest in repo - **verification = runnable commands + `python -c` assertions** (matches the repo's `verify_install.py` style; do NOT add a pytest suite).

**Design doc:** `docs/plans/2026-06-03-spikeinterface-menu-launcher-design.md`

**Preconditions:** Run all commands from the repo root `/Users/benfaib/Spike/SpikeInterface` with the data file set (`PFCM7_d0ephys_Block2.{ns2,ns5,nev}`) present and the saved analyzers under `outputs/tridesclous2/analyzer` and `outputs/spykingcircus2/analyzer` present (they are). Use `conda run -n si_env python ...` (non-interactive) so the env is active.

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/report.py` | Modify | Thread a `sorter_label` through `build_report` and the sorted-section labels (remove `tridesclous2` hardwiring). |
| `scripts/compare.py` | Create | Build `outputs/comparison.html` from `compare_two_sorters`; guard non-commensurate sorts. Reuses `report`'s HTML helpers. |
| `SpikeInterface_Menu.py` | Create (repo root) | The front-door launcher: status dashboard, interactive menu, arg-dispatch, all 7 actions. |
| `scripts/make_report.py` | Modify | Reduce to a thin shim that calls the launcher's `report` action. |
| `CLAUDE.md`, `README.md` | Modify | Document the launcher, `sigui`, `compare`, the shim. |

---

## Task 1: Make `scripts/report.py` sorter-aware

**Files:**
- Modify: `scripts/report.py` (lines 265, 275, 293, 366–369, 376)

- [ ] **Step 1: Verify the hardwiring exists (this is the "failing" state)**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import report; out=report.build_report(analyzer_dir='outputs/spykingcircus2/analyzer'); h=open(out).read(); print('tridesclous2 label present:', 'Sorted units (tridesclous2)' in h)"
```
Expected: `tridesclous2 label present: True` - i.e. a spykingcircus2 analyzer is wrongly labelled `tridesclous2`. This is the bug.

- [ ] **Step 2: Change the `build_report` signature (line 366)**

Replace:
```python
def build_report(data_dir=None, analyzer_dir=None, out_path=None) -> Path:
```
with:
```python
def build_report(data_dir=None, analyzer_dir=None, out_path=None, sorter_label=None) -> Path:
```

- [ ] **Step 3: Derive `sorter_label` after resolving `analyzer_dir` (lines 367–369)**

Replace:
```python
    analyzer_dir = Path(analyzer_dir) if analyzer_dir else DEFAULT_ANALYZER_DIR
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "report.html")
    OUTPUT_DIR.mkdir(exist_ok=True)
```
with:
```python
    analyzer_dir = Path(analyzer_dir) if analyzer_dir else DEFAULT_ANALYZER_DIR
    sorter_label = sorter_label or analyzer_dir.parent.name
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "report.html")
    OUTPUT_DIR.mkdir(exist_ok=True)
```

- [ ] **Step 4: Pass the label into the sorted section (line 376)**

Replace:
```python
        _safe_section("sorted", "Sorted units (tridesclous2)", _render_sorted, objects.get("analyzer")),
```
with:
```python
        _safe_section("sorted", f"Sorted units ({sorter_label})", _render_sorted, objects.get("analyzer"), sorter_label),
```
(`_safe_section(sec_id, title, render, *args)` forwards `*args` to `render`, so the extra `sorter_label` reaches `_render_sorted`.)

- [ ] **Step 5: Update `_render_sorted` to accept the label (line 265)**

Replace:
```python
def _render_sorted(analyzer) -> str:
```
with:
```python
def _render_sorted(analyzer, sorter_label) -> str:
```

- [ ] **Step 6: Use the label in the raster/rate title prefix (line 275)**

Replace:
```python
    raster, rate = _spike_figs(unit_ids, lambda u: sorting.get_unit_spike_train(u) / fs,
                               "Sorted (tridesclous2) units", total_duration=dur)
```
with:
```python
    raster, rate = _spike_figs(unit_ids, lambda u: sorting.get_unit_spike_train(u) / fs,
                               f"Sorted ({sorter_label}) units", total_duration=dur)
```

- [ ] **Step 7: Use the label in the section note (line 293)**

Replace:
```python
    return (f'<p class="note">Sorted with tridesclous2 over {dur:.1f}s sorted data, '
```
with:
```python
    return (f'<p class="note">Sorted with {sorter_label} over {dur:.1f}s sorted data, '
```

- [ ] **Step 8: Verify the label is now correct for both sorters**

Run:
```bash
conda run -n si_env python -c "
import sys; sys.path.insert(0,'scripts'); import report
for s in ('tridesclous2','spykingcircus2'):
    out = report.build_report(analyzer_dir=f'outputs/{s}/analyzer')
    h = open(out).read()
    assert f'Sorted units ({s})' in h, f'title not threaded for {s}'
    assert f'Sorted with {s} over' in h, f'note not threaded for {s}'
    print('OK', s)
# default no-arg call still labels tridesclous2
out = report.build_report(); h = open(out).read()
assert 'Sorted units (tridesclous2)' in h
print('OK default')
"
```
Expected: `OK tridesclous2`, `OK spykingcircus2`, `OK default`. (Note: this rebuilds `outputs/report.html` against spykingcircus2 last; that's fine - the launcher always passes the right `analyzer_dir`.)

- [ ] **Step 9: Commit**

```bash
git add scripts/report.py
git commit -m "fix(report): make build_report sorter-aware via sorter_label"
```

---

## Task 2: Create `scripts/compare.py` (sorter comparison → comparison.html)

**Files:**
- Create: `scripts/compare.py`

- [ ] **Step 1: Write the module**

Create `scripts/compare.py` with exactly:
```python
"""Build a standalone interactive comparison of the two sorters.

    conda activate si_env
    python scripts/compare.py            # builds outputs/comparison.html

Compares the saved tridesclous2 and spykingcircus2 sorts with SpikeInterface's
compare_two_sorters: an agreement-score heatmap + a matched/unmatched unit table.

IMPORTANT: the comparison is only meaningful if both sorts cover the SAME
recording window. Sorts are read from outputs/<sorter>/analyzer (the single
source of truth, same as report.py). If the two durations differ, the page shows
a clear caveat instead of a misleading matrix; re-sort both over a common window
first (the SpikeInterface_Menu.py 'compare' action offers to do this).
"""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import report  # noqa: E402  (reuse the HTML scaffolding helpers)

OUTPUT_DIR = bio.REPO_ROOT / "outputs"
DEFAULT_SORTERS = ("tridesclous2", "spykingcircus2")
DELTA_TIME_MS = 0.4   # coincidence window for a "match"
MATCH_SCORE = 0.5     # min agreement to call two units matched
# Two sorts whose durations differ by more than this (seconds) are treated as
# non-commensurate: comparing them would just measure the window mismatch.
DURATION_TOLERANCE_S = 1.0


def _load(sorter: str):
    """Return (sorting, duration_s) from outputs/<sorter>/analyzer, or (None, None)."""
    import spikeinterface.full as si

    analyzer_dir = OUTPUT_DIR / sorter / "analyzer"
    if not analyzer_dir.exists():
        return None, None
    a = si.load_sorting_analyzer(analyzer_dir)
    return a.sorting, float(a.get_total_duration())


def _heatmap(cmp) -> go.Figure:
    ag = cmp.get_ordered_agreement_scores()
    fig = go.Figure(go.Heatmap(
        z=ag.to_numpy(), x=[str(c) for c in ag.columns], y=[str(r) for r in ag.index],
        colorscale="Blues", zmin=0, zmax=1, colorbar=dict(title="agreement")))
    fig.update_layout(title="Agreement scores (Hungarian-ordered)",
                      xaxis_title=f"{cmp.sorting2_name} unit",
                      yaxis_title=f"{cmp.sorting1_name} unit",
                      height=480, margin=dict(t=40, b=40))
    return fig


def _match_table(cmp) -> str:
    # Hungarian optimal 1:1 assignment. The unmatched sentinel varies by
    # SpikeInterface version / dtype: it can be "" (empty string, the case in
    # 0.104.3) or -1, and matched partner ids may be ints or numeric strings.
    # int()-parsing handles every encoding: "" / None / NaN -> unmatched (int()
    # raises), -1 -> unmatched.
    hm = cmp.hungarian_match_12  # sorter1 unit id -> partner unit id

    def _partner(v):
        try:
            iv = int(v)
        except (TypeError, ValueError):
            return None
        return None if iv == -1 else iv

    rows = ""
    n_matched = 0
    for u1, u2 in hm.items():
        p = _partner(u2)
        if p is None:
            partner, frac = "-", 0.0
        else:
            partner, frac = str(p), cmp.get_agreement_fraction(u1, u2)
            n_matched += 1
        rows += f"<tr><td>{int(u1)}</td><td>{partner}</td><td>{frac:.3g}</td></tr>"
    n_unmatched = len(hm) - n_matched
    summary = (f'<p class="note">{n_matched} matched · {n_unmatched} unmatched '
               f'{cmp.sorting1_name} units · delta_time={DELTA_TIME_MS} ms · '
               f'match_score={MATCH_SCORE}. Click a header to sort.</p>')
    return (summary + '<table class="qc"><thead><tr>'
            f'<th onclick="sortTable(this.closest(\'table\'),0,true)">{cmp.sorting1_name} unit</th>'
            f'<th onclick="sortTable(this.closest(\'table\'),1,false)">{cmp.sorting2_name} match</th>'
            f'<th onclick="sortTable(this.closest(\'table\'),2,true)">agreement</th>'
            f'</tr></thead><tbody>' + rows + '</tbody></table>')


def build_comparison(data_dir=None, sorters=DEFAULT_SORTERS, out_path=None) -> Path:
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "comparison.html")
    OUTPUT_DIR.mkdir(exist_ok=True)
    s1_name, s2_name = sorters

    s1, d1 = _load(s1_name)
    s2, d2 = _load(s2_name)

    if s1 is None or s2 is None:
        missing = [n for n, s in [(s1_name, s1), (s2_name, s2)] if s is None]
        body = ('<div class="caveat">Cannot compare - no saved sort for: '
                f'{", ".join(missing)}. Run a sort for each sorter first.</div>')
    elif abs(d1 - d2) > DURATION_TOLERANCE_S:
        body = ('<div class="caveat">The two sorts cover different windows '
                f'({s1_name}: {d1:.1f}s, {s2_name}: {d2:.1f}s), so an agreement '
                'matrix would just measure the window mismatch, not genuine sorter '
                'disagreement. Re-sort both over the same window first.</div>')
    else:
        import spikeinterface.comparison as sc

        cmp = sc.compare_two_sorters(s1, s2, sorting1_name=s1_name, sorting2_name=s2_name,
                                     delta_time=DELTA_TIME_MS, match_score=MATCH_SCORE)
        body = (f'<p class="note">Both sorts cover {d1:.1f}s.</p>'
                + report._fig_html(_heatmap(cmp)) + _match_table(cmp))

    section = {"id": "compare", "title": f"{s1_name} vs {s2_name}", "html": body}
    out_path.write_text(report._html_document("Sorter comparison", [section]), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    print(build_comparison())
```

- [ ] **Step 2: Verify the rendering path with a synthetic comparison (deterministic, no sorting needed)**

Run:
```bash
conda run -n si_env python -c "
import sys; sys.path.insert(0,'scripts')
import spikeinterface.comparison as sc
from spikeinterface.core import generate_sorting
import compare
s1 = generate_sorting(num_units=5, durations=[10.0], seed=1)
s2 = generate_sorting(num_units=5, durations=[10.0], seed=2)
cmp = sc.compare_two_sorters(s1, s2, sorting1_name='a', sorting2_name='b')
hm = compare._heatmap(cmp)
assert 'heatmap' in hm.to_html(full_html=False, include_plotlyjs=False).lower()
t = compare._match_table(cmp)
assert 'agreement' in t and 'a unit' in t
print('OK rendering')
"
```
Expected: `OK rendering`. (Confirms `_heatmap` and `_match_table` work against a real `SymmetricSortingComparison`, including `get_ordered_agreement_scores`, `hungarian_match_12`, `get_agreement_fraction`, `sorting1_name`/`sorting2_name`.)

- [ ] **Step 3: Verify the duration-mismatch caveat path against the real saved sorts**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import compare; out=compare.build_comparison(); h=open(out).read(); print('caveat shown:', 'different windows' in h); print(out)"
```
Expected: `caveat shown: True` (the current sorts are 132 s vs 10 s) and the `outputs/comparison.html` path. Confirms the guard fires instead of producing a misleading matrix.

- [ ] **Step 4: Commit**

```bash
git add scripts/compare.py
git commit -m "feat(compare): standalone sorter-comparison report (comparison.html)"
```

---

## Task 3: Create the launcher `SpikeInterface_Menu.py` (non-Qt actions)

**Files:**
- Create: `SpikeInterface_Menu.py` (repo root)

- [ ] **Step 1: Write the launcher**

Create `SpikeInterface_Menu.py` at the repo root with exactly:
```python
#!/usr/bin/env python
"""PFCM7 SpikeInterface workspace - single front-door menu launcher.

    conda activate si_env
    python SpikeInterface_Menu.py            # interactive status + menu
    python SpikeInterface_Menu.py report     # run one action directly, then exit
    python SpikeInterface_Menu.py --help

Run with no action -> prints a pipeline-status dashboard and a numbered menu
(friendly for everyone). Run with an action -> dispatches it directly (handy for
scripting). Heavy SpikeInterface imports are lazy, so the menu stays responsive.

Actions:
    explore   quick static figures (LFP + .nev) via scripts/explore_data.py
    sort      spike-sort the broadband via scripts/run_sorting.py
    report    build + open the interactive HTML report (scripts/report.py)
    gui       open spikeinterface-gui on the saved sort
    traces    scroll raw broadband traces in ephyviewer
    compare   agreement matrix between the two sorters (scripts/compare.py)
    verify    environment smoke test (scripts/verify_install.py)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import blackrock_io as bio  # noqa: E402
import report  # noqa: E402
from run_sorting import SORTERS  # noqa: E402  (single-source the sorter list)

QUICK_SECONDS = 30
ACTIONS = ["explore", "sort", "report", "gui", "traces", "compare", "verify"]
# Actions that open a blocking Qt window: the menu launches them in a fresh
# child process so the menu survives and Qt gets a clean process each time.
QT_ACTIONS = {"gui", "traces"}


def _analyzer_dir(sorter: str) -> Path:
    return bio.REPO_ROOT / "outputs" / sorter / "analyzer"


def _status(data_dir, sorter: str) -> None:
    _objects, rows = report._gather(data_dir, _analyzer_dir(sorter))
    print(f"\nPFCM7 workspace · active sorter: {sorter}")
    for r in rows:
        print(f"  [{r['status']:4}] {r['stage']:22} {r['detail']}")


def _shell(script: str, *flags: str) -> bool:
    """Run a sibling script as a child process, inheriting stdout (live output)."""
    cmd = [sys.executable, str(SCRIPTS / script), *flags]
    print(f"\n$ {' '.join(cmd)}\n")
    return subprocess.run(cmd).returncode == 0


def _self(action: str, args) -> bool:
    """Re-invoke this launcher in a child process for a single (blocking Qt) action."""
    cmd = [sys.executable, str(ROOT / "SpikeInterface_Menu.py"), action, "--sorter", args.sorter]
    if args.data_dir:
        cmd += ["--data-dir", args.data_dir]
    print(f"\n$ {' '.join(cmd)}\n")
    return subprocess.run(cmd).returncode == 0


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def action_explore(args) -> bool:
    flags = ["--data-dir", args.data_dir] if args.data_dir else []
    return _shell("explore_data.py", *flags)


def action_sort(args) -> bool:
    flags = ["--sorter", args.sorter]
    if args.duration is not None:
        flags += ["--duration", str(args.duration)]
    if args.data_dir:
        flags += ["--data-dir", args.data_dir]
    return _shell("run_sorting.py", *flags)


def action_verify(args) -> bool:
    return _shell("verify_install.py")  # takes no flags


def action_report(args) -> bool:
    out = report.build_report(data_dir=args.data_dir, analyzer_dir=_analyzer_dir(args.sorter),
                              sorter_label=args.sorter)
    uri = out.resolve().as_uri()
    print(f"\nReport written: {out}\nOpen it:        {uri}")
    if sys.stdin.isatty():
        try:
            if not webbrowser.open(uri):
                print("(could not open a browser automatically - open the link above)")
        except Exception:  # noqa: BLE001
            pass
    return True


def action_gui(args) -> bool:
    analyzer_dir = _analyzer_dir(args.sorter)
    if not analyzer_dir.exists():
        print(f"No saved sort for {args.sorter} - run 'sort' first.")
        return False
    try:
        import spikeinterface.full as si
        import spikeinterface_gui as sigui
    except Exception as e:  # noqa: BLE001
        print(f"Could not import the GUI ({e!r}). Try: python scripts/verify_install.py")
        return False
    print(f"Opening spikeinterface-gui on {analyzer_dir} (close the window to return) ...")
    analyzer = si.load_sorting_analyzer(analyzer_dir)
    sigui.run_mainwindow(analyzer, mode="desktop")  # blocks until the window closes
    return True


def action_traces(args) -> bool:
    try:
        import spikeinterface.widgets as sw
    except Exception as e:  # noqa: BLE001
        print(f"Could not import the trace viewer ({e!r}). Try: python scripts/verify_install.py")
        return False
    print("Opening ephyviewer on the broadband recording (close the window to return) ...")
    rec = bio.read_broadband(args.data_dir)
    sw.plot_traces({"broadband": rec}, backend="ephyviewer", show_channel_ids=True)  # blocks
    return True


def action_compare(args) -> bool:
    import compare  # lazy: pulls in spikeinterface

    other = [s for s in SORTERS if s != args.sorter]
    sorters = (args.sorter, other[0]) if other else tuple(SORTERS[:2])

    # Surface a duration mismatch and (interactively) offer to make the two sorts
    # commensurate by re-sorting both over a common window before comparing.
    durations = {}
    for s in sorters:
        a_dir = _analyzer_dir(s)
        if a_dir.exists():
            import spikeinterface.full as si
            durations[s] = float(si.load_sorting_analyzer(a_dir).get_total_duration())
    mismatch = (len(durations) == 2
                and abs(durations[sorters[0]] - durations[sorters[1]]) > compare.DURATION_TOLERANCE_S)
    if mismatch:
        print("\nThe two sorts cover different windows: "
              + ", ".join(f"{s}={d:.1f}s" for s, d in durations.items()) + ".")
        if sys.stdin.isatty() and input(
                f"Re-sort both over the first {QUICK_SECONDS}s to compare? [y/N] ").strip().lower() == "y":
            for s in sorters:
                _shell("run_sorting.py", "--sorter", s, "--duration", str(QUICK_SECONDS),
                       *(["--data-dir", args.data_dir] if args.data_dir else []))

    out = compare.build_comparison(data_dir=args.data_dir, sorters=sorters)
    uri = out.resolve().as_uri()
    print(f"\nComparison written: {out}\nOpen it:            {uri}")
    if sys.stdin.isatty():
        try:
            webbrowser.open(uri)
        except Exception:  # noqa: BLE001
            pass
    return True


DISPATCH = {
    "explore": action_explore, "sort": action_sort, "report": action_report,
    "gui": action_gui, "traces": action_traces, "compare": action_compare,
    "verify": action_verify,
}

_MENU = [
    ("1", "explore", "Explore raw data         quick static figures (LFP + .nev)"),
    ("2", "sort",    "Run / re-run sorting     tridesclous2 or spykingcircus2"),
    ("3", "report",  "Build & open report      interactive HTML -> browser"),
    ("4", "gui",     "Open GUI inspector       spikeinterface-gui on the saved sort"),
    ("5", "traces",  "Scroll raw traces        ephyviewer trace browser"),
    ("6", "compare", "Compare the two sorters  agreement matrix"),
    ("7", "verify",  "Verify install"),
]


def _menu(args) -> int:
    if not sys.stdin.isatty():
        print("\n(non-interactive stdin -> building the report)")
        return 0 if DISPATCH["report"](args) else 1
    while True:
        print()
        for key, _action, label in _MENU:
            print(f"  {key}) {label}")
        print("  t) Switch active sorter")
        print("  q) Quit")
        choice = input("> ").strip().lower()
        if choice in ("q", ""):
            return 0
        if choice == "t":
            args.sorter = SORTERS[(SORTERS.index(args.sorter) + 1) % len(SORTERS)]
            _status(args.data_dir, args.sorter)
            continue
        action = next((a for k, a, _ in _MENU if k == choice), None)
        if action is None:
            print("Unknown choice.")
            continue
        if action == "sort":
            args.duration = (QUICK_SECONDS
                             if input(f"Quick {QUICK_SECONDS}s test? [y/N] ").strip().lower() == "y"
                             else None)
        if action in QT_ACTIONS:
            _self(action, args)        # fresh child process for the blocking Qt window
        else:
            DISPATCH[action](args)
        _status(args.data_dir, args.sorter)


def main() -> int:
    bio.use_utf8_stdout()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", nargs="?", choices=ACTIONS, default=None,
                        help="Run one action directly (default: interactive menu).")
    parser.add_argument("--data-dir", default=None, help="Folder with the .nev/.nsX (default: repo root).")
    parser.add_argument("--sorter", choices=SORTERS, default=SORTERS[0], help="Active sorter.")
    parser.add_argument("--duration", type=float, default=None, help="For 'sort': first N seconds only.")
    args = parser.parse_args()

    if args.action is None:
        _status(args.data_dir, args.sorter)
        return _menu(args)
    ok = DISPATCH[args.action](args)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify `--help` and that the module imports cleanly**

Run:
```bash
conda run -n si_env python SpikeInterface_Menu.py --help
```
Expected: argparse help listing the positional `action` choices (`explore sort report gui traces compare verify`) and `--data-dir/--sorter/--duration`, exit 0. (Confirms `from run_sorting import SORTERS` and the `report` import succeed.)

- [ ] **Step 3: Verify the non-interactive default path (builds the report)**

Run:
```bash
printf '' | conda run -n si_env python SpikeInterface_Menu.py
```
Expected: the status dashboard (`PFCM7 workspace · active sorter: tridesclous2` + `[PASS]`/`[SKIP]` rows), then `(non-interactive stdin -> building the report)` and `Report written: .../outputs/report.html`. Exit 0. (No browser opens - stdin is not a TTY.)

- [ ] **Step 4: Verify arg-dispatch of `report` labels with the chosen sorter**

Run:
```bash
conda run -n si_env python SpikeInterface_Menu.py report --sorter spykingcircus2 < /dev/null && grep -c "Sorted units (spykingcircus2)" outputs/report.html
```
Expected: `Report written: ...` printed, then `1` from grep (the report is labelled spykingcircus2). Confirms the Task 1 plumbing flows through the launcher.

- [ ] **Step 5: Verify arg-dispatch of `verify` shells out correctly**

Run:
```bash
conda run -n si_env python SpikeInterface_Menu.py verify < /dev/null
```
Expected: prints `$ .../python .../scripts/verify_install.py` then `verify_install.py`'s normal version/summary output, exit 0. (Confirms `verify` is called with no extra flags.)

- [ ] **Step 6: Manual check (interactive menu - needs a real terminal)**

In a real terminal (not pipeable), run `conda run -n si_env python SpikeInterface_Menu.py`, confirm the numbered menu renders, press `t` and confirm the header sorter toggles tridesclous2 ⇄ spykingcircus2, then `q` to quit. (The TTY menu can't be exercised by a pipe because `sys.stdin.isatty()` is then False - that path is covered by Step 3.)

- [ ] **Step 7: Commit**

```bash
git add SpikeInterface_Menu.py
git commit -m "feat: SpikeInterface_Menu.py launcher (status dashboard + menu + explore/sort/report/verify)"
```

---

## Task 4: Verify the Qt actions (gui, traces) in the launcher

The code for `action_gui` / `action_traces` / `QT_ACTIONS` / `_self` was written in Task 3. This task verifies them headless. No code changes unless a verification fails.

**Files:**
- (verify only) `SpikeInterface_Menu.py`

- [ ] **Step 1: Verify the GUI inspector launches on the saved analyzer (headless)**

Run:
```bash
QT_QPA_PLATFORM=offscreen timeout 60 conda run -n si_env python SpikeInterface_Menu.py gui --sorter tridesclous2 < /dev/null; echo "exit=$?"
```
Expected: prints `Opening spikeinterface-gui on .../outputs/tridesclous2/analyzer ...`, loads the analyzer (may take a few seconds to lazy-compute extensions), opens the offscreen window, then is killed by `timeout` → `exit=124`. **`exit=124` is success** here - it means the GUI reached its event loop without an import/load error. (An import or load failure would print the error and exit non-124 quickly.)

- [ ] **Step 2: Verify the GUI guard when no analyzer exists**

Run:
```bash
conda run -n si_env python SpikeInterface_Menu.py gui --sorter spykingcircus2 --data-dir /tmp/does-not-exist < /dev/null 2>&1 | head -3; echo "---"
QT_QPA_PLATFORM=offscreen timeout 60 conda run -n si_env python -c "
import sys; sys.path.insert(0,'.'); import importlib.util
spec=importlib.util.spec_from_file_location('m','SpikeInterface_Menu.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class A: sorter='nosuchsorter'; data_dir=None
print('returned', m.action_gui(A()))
"
```
Expected: the second command prints `No saved sort for nosuchsorter - run 'sort' first.` and `returned False`. (Confirms the `analyzer_dir.exists()` guard; the `nosuchsorter` analyzer dir does not exist.)

- [ ] **Step 3: Verify the ephyviewer trace browser launches (headless)**

Run:
```bash
QT_QPA_PLATFORM=offscreen timeout 60 conda run -n si_env python SpikeInterface_Menu.py traces < /dev/null; echo "exit=$?"
```
Expected: prints `Opening ephyviewer on the broadband recording ...`, loads the broadband, opens the offscreen window, killed by `timeout` → `exit=124` (success, same reasoning as Step 1). Confirms the `plot_traces(..., backend="ephyviewer")` path works and the broken `ephyviewer` CLI is avoided.

- [ ] **Step 4: Commit (only if a fix was needed; otherwise skip)**

```bash
git add SpikeInterface_Menu.py
git commit -m "fix: Qt action launch (gui/traces) adjustments from headless verification"
```
If Steps 1–3 passed with no edits, there is nothing to commit - note that and move on.

---

## Task 5: Verify the compare action (launcher → compare.py)

`action_compare` was written in Task 3 and `compare.py` in Task 2. This task verifies the wiring end-to-end. No code changes unless a verification fails.

**Files:**
- (verify only) `SpikeInterface_Menu.py`, `scripts/compare.py`

- [ ] **Step 1: Verify non-interactive compare emits the duration-mismatch caveat**

Run:
```bash
conda run -n si_env python SpikeInterface_Menu.py compare < /dev/null
grep -c "different windows" outputs/comparison.html
```
Expected: the launcher prints the differing-windows line and `Comparison written: .../outputs/comparison.html`; the `grep` prints `1`. (Non-interactive stdin → no re-sort prompt → the caveat is rendered, never a misleading matrix.)

- [ ] **Step 2: (Optional, slow ~minutes) Verify a real agreement matrix after making sorts commensurate**

Only run if you want to confirm the matrix path end-to-end on real data:
```bash
conda run -n si_env python SpikeInterface_Menu.py sort --sorter tridesclous2 --duration 30 --verbosity quiet < /dev/null
conda run -n si_env python SpikeInterface_Menu.py sort --sorter spykingcircus2 --duration 30 --verbosity quiet < /dev/null
conda run -n si_env python scripts/compare.py
grep -c "Agreement scores" outputs/comparison.html
```
Wait - `action_sort` does not pass `--verbosity`; call `run_sorting.py` directly for the quiet flag:
```bash
conda run -n si_env python scripts/run_sorting.py --sorter tridesclous2 --duration 30 --verbosity quiet
conda run -n si_env python scripts/run_sorting.py --sorter spykingcircus2 --duration 30 --verbosity quiet
conda run -n si_env python scripts/compare.py
grep -c "Agreement scores" outputs/comparison.html
```
Expected: after both 30 s sorts, `grep` prints `1` (the heatmap title is present → the matrix rendered because durations now match within tolerance). This overwrites both analyzers with 30 s sorts; re-run a full sort later if you want the full results back.

- [ ] **Step 3: Commit (only if a fix was needed; otherwise skip)**

```bash
git add SpikeInterface_Menu.py scripts/compare.py
git commit -m "fix: compare action wiring adjustments from verification"
```

---

## Task 6: Reduce `scripts/make_report.py` to a thin shim

**Files:**
- Modify: `scripts/make_report.py` (replace entire contents)

- [ ] **Step 1: Replace the file contents**

Overwrite `scripts/make_report.py` with exactly:
```python
"""Thin shim - the report flow now lives in the root SpikeInterface_Menu.py.

    conda activate si_env
    python scripts/make_report.py                 # builds + opens the report
    python scripts/make_report.py --data-dir DIR
    python scripts/make_report.py --sorter spykingcircus2

Kept for backwards compatibility; it just invokes the launcher's 'report'
action with whatever flags you pass. For the full menu (sort / GUI / compare /
trace browser / ...), run the launcher directly:

    python SpikeInterface_Menu.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent.parent / "SpikeInterface_Menu.py"


def main() -> int:
    cmd = [sys.executable, str(LAUNCHER), "report", *sys.argv[1:]]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the shim still builds the report and forwards flags**

Run:
```bash
conda run -n si_env python scripts/make_report.py --sorter spykingcircus2 < /dev/null
grep -c "Sorted units (spykingcircus2)" outputs/report.html
```
Expected: `Report written: .../outputs/report.html` printed by the launcher, then `1` from grep (flag forwarded → spykingcircus2 label). Confirms backwards compatibility.

- [ ] **Step 3: Verify a bad flag surfaces the launcher's argparse error (forwarding works)**

Run:
```bash
conda run -n si_env python scripts/make_report.py --sorter nope < /dev/null 2>&1 | tail -2; echo "exit=${PIPESTATUS[0]}"
```
Expected: an argparse error mentioning invalid choice `nope` for `--sorter`, and a non-zero exit. (Confirms `sys.argv[1:]` is forwarded into the launcher.)

- [ ] **Step 4: Commit**

```bash
git add scripts/make_report.py
git commit -m "refactor(make_report): reduce to thin shim over SpikeInterface_Menu.py"
```

---

## Task 7: Update docs (CLAUDE.md + README.md)

**Files:**
- Modify: `CLAUDE.md` (Commands section + Architecture intro)
- Modify: `README.md` (add a "Quick start: the menu" note near the top of usage)

- [ ] **Step 1: Add the launcher to the top of the CLAUDE.md `## Commands` code block**

In `CLAUDE.md`, find the ```` ```bash ```` block under `## Commands` that begins with `conda activate si_env`. Immediately after the `conda activate si_env` line, insert:
```bash
python SpikeInterface_Menu.py          # ⭐ single front door: status dashboard + menu (explore/sort/report/gui/traces/compare/verify)
python SpikeInterface_Menu.py report   # or run one action directly: explore|sort|report|gui|traces|compare|verify
python SpikeInterface_Menu.py gui --sorter tridesclous2   # spikeinterface-gui (sigui) on the saved sort
```

- [ ] **Step 2: Document `compare.py` / `comparison.html` in the same Commands block**

In the same block, after the `make_report.py` lines, insert:
```bash
python scripts/compare.py              # agreement matrix between the two sorters -> outputs/comparison.html
```

- [ ] **Step 3: Add an Architecture note for the launcher + compare**

In `CLAUDE.md`, in the `## Architecture` section, after the paragraph describing `scripts/report.py` / `make_report.py`, add this paragraph:
```markdown
`SpikeInterface_Menu.py` (repo **root**, not `scripts/`) is the single front-door
launcher: run bare it prints a status dashboard (via `report._gather`) + a
numbered menu; run with an action (`report`, `sort`, `gui`, `traces`, `compare`,
`verify`, `explore`) it dispatches directly. It shells out to the `scripts/*.py`
for explore/sort/verify (live stdout), calls `report.build_report(...)`
in-process, and launches the **blocking** Qt GUIs in fresh child processes
(`_self`): the inspector is `spikeinterface-gui` (console command **`sigui
<analyzer_dir>`**, not `spikeinterface-gui`) and the trace browser is
`plot_traces(..., backend="ephyviewer")`. `make_report.py` is now a thin shim
over the launcher's `report` action. `scripts/compare.py` builds a standalone
`outputs/comparison.html` from `compare_two_sorters`; it refuses to draw a
misleading matrix when the two sorts cover different windows (the launcher's
`compare` action offers to re-sort both over a common window first). The Qt
binding in `si_env` is **PyQt5** (the `PySide6<6.8` pin is satisfied by a pip
install but the conda env resolves to PyQt5; either works).
```

- [ ] **Step 4: Add a "Quick start" pointer to README.md**

In `README.md`, find the first usage code block (the one after first-time setup, beginning with `conda activate si_env`). Immediately before it, add:
```markdown
### Quick start - the menu

Once set up, the simplest way in is the single launcher at the repo root:

```bash
conda activate si_env
python SpikeInterface_Menu.py        # status dashboard + a numbered menu
```

Pick a number to explore the data, run a sort, build & open the interactive HTML
report, open the `spikeinterface-gui` inspector, scroll raw traces, or compare
the two sorters. Power users can run a single action directly, e.g.
`python SpikeInterface_Menu.py report` or `python SpikeInterface_Menu.py gui`.
```

- [ ] **Step 5: Verify the docs mention the new entry points**

Run:
```bash
grep -c "SpikeInterface_Menu.py" CLAUDE.md README.md
grep -c "sigui" CLAUDE.md
grep -c "compare.py" CLAUDE.md
```
Expected: each `grep -c` prints a count `>= 1` for both files / patterns (CLAUDE.md count for `SpikeInterface_Menu.py` will be several).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: document SpikeInterface_Menu launcher, sigui, compare, make_report shim"
```

---

## Self-review notes (author)

- **Spec coverage:** single launcher (Task 3/4/5), sorter-aware report (Task 1), compare → comparison.html (Task 2/5), GUI inspector + traces (Task 4), polish: auto-open report on TTY (Task 3 `action_report`), make_report shim (Task 6), docs incl. PyQt5/sigui (Task 7). All design sections mapped.
- **Type/name consistency:** `build_report(..., sorter_label=...)` defined in Task 1 and called with `sorter_label=` in Task 3. `compare.build_comparison(data_dir, sorters, out_path)` and `compare.DURATION_TOLERANCE_S` defined in Task 2, used in Task 3's `action_compare`. `SORTERS` imported from `run_sorting` (a list). `report._gather`, `report._fig_html`, `report._html_document` are existing names used by `compare.py` and the launcher.
- **Known limitation surfaced, not hidden:** the interactive TTY menu (Task 3 Step 6) is a manual check because `isatty()` is False under a pipe; the non-interactive default and all arg-dispatch paths are auto-verified.
- **No pytest:** intentional - repo has no test framework; verification is runnable commands, consistent with `verify_install.py`.
