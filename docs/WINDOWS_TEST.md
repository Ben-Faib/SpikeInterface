# Testing Spike 2.0 on Windows

The lab will run this workbench on Windows, and a Mac cannot prove it works there. This
page is the whole Windows check: about 20 minutes of setup the first time, then one
command (about 5 minutes) plus ten minutes of looking at the app.

## What only a Windows run can prove

- The terminal app draws correctly in Windows Terminal: the rail, the boxes, the block
  characters of the waveforms and the SPIKE wordmark.
- Cancelling a sort or a task really stops it. Windows kills child processes differently
  from macOS (`taskkill /T`), and SpikeInterface starts worker processes of its own.
- Paths with spaces or backslashes, and a UTF-8 console on a machine whose default code
  page is not UTF-8 (µ, ✓ and · are printed everywhere).
- The two desktop windows (the spikeinterface-gui inspector and the trace viewer) open
  from the app and give control back when closed.
- Docker Desktop on Windows, if you use Docker sorters.

## 1. Set up (once)

In **PowerShell** (press Win, type PowerShell, Enter):

```powershell
winget install --id=astral-sh.uv -e
```

Close and reopen PowerShell, then get the project and the environment:

```powershell
git clone <repo-url> SpikeInterface
cd SpikeInterface
uv sync --group dev
```

`uv sync` downloads Python 3.12 and every dependency as prebuilt wheels: no compiler, no
conda. The first run takes 5-10 minutes (PySide6 is large).

Copy the three recording files into the project folder, next to `pyproject.toml`:
`PFCM7_d0ephys_Block2.ns5`, `.ns2` and `.nev`. (A recording elsewhere works too: add
`--data-dir C:\path\to\folder` to the commands below.)

Check the install:

```powershell
uv run python scripts\verify_install.py
```

It ends with "All good - SpikeInterface can read your data. ✓".

## 2. The automatic check

```powershell
uv run python scripts\check_workbench.py
```

This drives every function of the workbench against the real recording: loading, the
probe, settings, a quick sort (with the ~4 µV noise-floor check), explore, judging,
apply, the report, the Phy export, a comparison, reproducing a run, the run recipe, and
every screen of the app. It works in a **temporary copy** of the project, so it never
touches your saved sorts, labels or settings.

Every line should read **PASS**, except gui and traces, which read **MANUAL** because
they open desktop windows (step 3 covers them). The command exits with code 0 when
nothing failed.

## 3. Look at the app (10 minutes)

Double-click **`run.bat`** in the project folder (or run `.\run.bat`). Use **Windows
Terminal** if it is installed: the older console host draws some characters badly.

| Do this | You should see |
|---|---|
| Launch | The SPIKE wordmark and a short checklist, then Home. Any key skips the splash. |
| Look at the top | The rail: `1 Data · 2 Probe · 3 Sort · 4 Judge · 5 Apply · 6 Share` joined by lines, each with ✓ / ! / ·. |
| Press `1` … `6`, then `Esc` | Each stage appears under the rail; `Esc` returns to Home and never quits. |
| Press `,` | Settings. Highlight "Band-pass low (Hz)", press Enter, type `250`, Enter: the row shows 250 with "default 300". Press `d` to put it back. |
| Press `2` | The probe drawn as a shank, every value listed. Press `e`: an editor for a copy of the built-in probe. `Esc` to cancel. |
| Press `3`, then `t` | A quick 30 s sort with a live checklist and clock. Press `Esc` partway: it stops. Open Task Manager: no leftover `python.exe` from the sort. |
| Press `t` again and let it finish | A result card with the unit count and the noise floor (about 4 µV). |
| Press `4` | Units listed; the card on the right shows waveforms drawn in blocks, a histogram, and an amplitude line. Press `g` on one unit: it is labelled and the cursor moves on. |
| Press `v` on 4 Judge | The browser opens that unit's page: spikes over the template, correlograms, amplitude over time, features. `j` / `k` move between units. |
| Press `i` on 4 Judge | The spikeinterface-gui window opens. Close it: the app comes back. |
| Press `1`, then `t` | The trace viewer opens. Close it: the app comes back. |
| Press `6`, highlight Report, Enter | The report builds, then opens in the browser. |
| Press `/`, type `repro`, Enter | Reproduce: the sort re-runs from its recipe, then a table of values with verdicts. |

## 4. What to send back

- The output of `scripts\check_workbench.py` (copy the terminal text).
- For anything that looked wrong: a screenshot, and the matching log from
  `outputs\logs\` (every task the app runs writes one there) or `outputs\<sorter>\sort.log`.

## Troubleshooting

- **"No module named …"**: run `uv sync --group dev` in the project folder, and start
  things with `uv run python …` or `run.bat`. There is nothing to activate.
- **Boxes or blocks look broken**: use Windows Terminal, and a font with box-drawing
  characters (Cascadia Mono, the default there, works).
- **A sort cannot start because Docker is not running**: only Docker sorters need it.
  The four built-in sorters (tridesclous2, spykingcircus2, lupin, simple) never do.
- **GPU sorters (Kilosort4)** are not offered yet, even on a machine with an NVIDIA GPU.
  Enabling them is the separate lab-deployment track (`goals/GOAL_WD_DEPLOY.md`).
