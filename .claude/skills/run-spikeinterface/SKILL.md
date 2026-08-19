---
name: run-spikeinterface
description: Use when asked to run, launch, start, smoke-test, or verify that this repo's SpikeInterface menu app (SpikeInterface_Menu.py) works - covers the uv environment bootstrap and a headless launch check for the Textual TUI on Windows.
---

# Run the SpikeInterface menu

The front door is `SpikeInterface_Menu.py` (repo root). Bare, it opens a
full-screen **Textual** TUI dashboard; with an action arg it dispatches directly.
The environment is **uv**-managed (Python 3.12 + `uv.lock`). Follow the verified
path below - every command here has been run and confirmed on this machine.

## 1. Bootstrap the environment

`uv` is the primary tool but is **not always on PATH** (it installs to
`C:\Users\Ben\.local\bin`). Prepend it for the session first, and install uv only
if it is missing:

```powershell
$env:Path = "C:\Users\Ben\.local\bin;$env:Path"
uv --version   # if "not recognized" -> install it:
#   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv sync        # builds .venv from uv.lock (Python 3.12 + full SpikeInterface stack)
```

`.venv` and `uv.lock` are the source of truth; a fresh clone has neither `.venv`
nor `uv` until you do the above. Conda fallback: `conda env create -f environment.yml`.

## 2. Launch (interactive)

```powershell
uv run python SpikeInterface_Menu.py           # the TUI dashboard
uv run python SpikeInterface_Menu.py report    # or one action directly: explore|sort|report|gui|traces|compare|verify
```

The dashboard opens with a red **"no recording"** banner until the
`PFCM7_d0ephys_Block2.{ns2,ns5,nev}` set is in the repo root - the raw files are
git-ignored, so this is normal on a clean tree (press `d` in-app for the checklist).

## 3. Verify it launches (headless - no real terminal needed)

A Textual TUI can't be confirmed by piping stdout (it needs a TTY, and a
non-interactive `SpikeInterface_Menu.py` bare-run just builds the report instead).
Two headless checks actually mount the app:

```powershell
uv run python -m pytest tests/ -q                              # 255+ Pilot/unit tests
uv run python .claude/skills/run-spikeinterface/verify_launch.py   # drives the REAL SpikeMenuApp
```

`verify_launch.py` mounts `SpikeMenuApp` via Textual's Pilot, dismisses the
first-run modal, snapshots every panel (title / data banner / sorters / actions /
footer) to `outputs/menu_launch_capture.txt` + an SVG, exercises navigation, and
exits non-zero if the menu fails to mount. Read the capture file to eyeball the
rendered dashboard.

## Known gotchas (all hit on this machine)

| Symptom | Cause / fix |
|---|---|
| `uv : command not found` / not recognized | Not on PATH. `$env:Path = "C:\Users\Ben\.local\bin;$env:Path"` (or restart shell). |
| `pytest`: `test_sort_progress_surfaces_real_error_from_log` FAILS (`WinError 2`) | Windows-only artifact - that test hard-codes `sh -c`, and `sh` isn't on Windows. Not an app defect; every app-mount test passes. |
| `verify_install.py` / menu says "No Blackrock files" | Expected - raw `.ns5/.ns2/.nev` are git-ignored. Drop the recording set in the repo root or pass `--data-dir`. |
| `UnicodeEncodeError: 'charmap'` when printing app widgets | Textual captures stdout as cp1252 during a run. Collect text and write it UTF-8 *after* the app closes (this is what `verify_launch.py` does). |
| Bare run in a non-interactive shell builds a report instead of the menu | By design: `_menu()` sees `stdin` isn't a TTY and falls back. Use `verify_launch.py` to test the actual TUI. |
