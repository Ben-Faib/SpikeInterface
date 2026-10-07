# Start here: the Windows audit of Spike 2.0

Spike 2.0 lives on the branch **`Version-2`**. It has passed every automatic check on a
Mac; nothing has run on Windows yet. This page hands the whole Windows audit to a Claude
Code session on the lab machine. `START_HERE_WINDOWS.html` is the same content with copy buttons
(`scripts/start_here_page.py` rebuilds it from this file).

## Ben: three steps

1. **Get the branch** (PowerShell, in the folder where the project should live):

   ```powershell
   git clone -b Version-2 https://github.com/Ben-Faib/SpikeInterface.git
   cd SpikeInterface
   ```

   Already cloned? `git fetch origin` then `git switch Version-2`.

2. **Put the recording in that folder**, next to `pyproject.toml`:
   `PFCM7_d0ephys_Block2.ns5`, `.ns2` and `.nev` (not in git; the `.ns5` is ~176 MB).

3. **Open Claude Code in that folder and paste the prompt below.** Leave it running;
   it takes about an hour and ends with a report in `docs\audits\`.

## The prompt

```text
Audit Spike 2.0 on this Windows machine before it goes to the lab, functionally and
visually, and write up what you find.

Where things are: this repo, branch Version-2. Read CLAUDE.md and docs/INVARIANTS.md (the rules, and the
~4 µV noise-floor canary), goals/GOAL_V2.md (what Spike 2.0 is meant to do - the spec
to audit against), docs/WINDOWS_TEST.md (what a person would check by hand) and this
file, START_HERE_WINDOWS.md. The recording should be in the repo root; if the three
PFCM7_d0ephys_Block2 files are missing, ask me where they are.

What to cover:
1. Environment. Install the project environment with `uv sync --group dev` (if uv
   itself is missing, give me the one install command rather than installing it).
   Record the Windows version, terminal (Windows Terminal or the classic console),
   Python, whether an NVIDIA GPU is present, and whether Docker is installed.
2. Automatic checks: the test suite (`uv run python -m pytest tests -q`), the
   end-to-end harness (`uv run python scripts\check_workbench.py`), and the launch
   check (`uv run python .claude\skills\run-spikeinterface\verify_launch.py`).
3. What the app draws: `uv run python scripts\visual_audit.py` renders every screen at
   four terminal sizes into outputs\visual_audit\ (index.html is the gallery; open it
   in your browser pane if you have one, or look at the SVGs). Look at every image.
4. How this machine's terminal draws it:
   `powershell -ExecutionPolicy Bypass -File scripts\windows\terminal_screenshots.ps1`
   runs the app in a real window, steps through every screen and saves PNGs to
   outputs\visual_audit\terminal\. It was written on a Mac and has never run on
   Windows; if it misbehaves, fix it and say what you changed. Look at every PNG and
   compare it with the rendered version of the same screen.
5. What only a real Windows session can show: cancelling a sort (3 Sort, t, then Esc
   partway) really stops it, with no python.exe left behind; the spikeinterface-gui
   inspector (4 Judge, i) and the trace viewer (1 Data, t) open and hand control back
   when closed - screenshot each window; v on 4 Judge opens the unit pages in the
   browser at that unit (screenshot it and judge whether the plots are good enough
   to label a unit by); the report opens in the browser; the app
   works in both Windows Terminal and the classic console; a project path containing a
   space works (copy the project to such a folder and run the harness there).
6. Every row of the table in docs\WINDOWS_TEST.md.

Visually, judge each screen for: the rail's six chips on one line, joined, with their
captions underneath; boxes and lines drawn as solid lines, not ? or empty squares;
the SPIKE wordmark, waveforms and histograms drawn as solid blocks without gaps; no
list row or key line wrapping onto a second line or cut mid-word; nothing clipped at
80x24; the highlighted row visible; colour used as a role (green only for done or
verified, amber for needs-attention, red for failure); text readable against the
background. Compare with goals/GOAL_V2.md and the mockups it links.

Report every issue you find, including ones you are unsure of or think minor; do not
filter for importance. For each: severity (blocker / should-fix / nit), your
confidence, how to reproduce, the screenshot that shows it, and whether you fixed it.

Scope: audit everything above. Fix only what is clearly a bug - Windows-specific
breakage, a crash, or behaviour that contradicts the docs - with the smallest change,
a test where this repo keeps tests for that kind of change, and a commit on
Version-2 (descriptive message, explicit paths, no em dashes anywhere - the repo
pins that with a test). Anything that is a design or judgment call goes in the
report, not into the code. Do not push, merge, delete files or branches, change my
saved settings, or install software other than the uv environment without asking.
check_workbench.py works in a throwaway copy; keep it that way.

Deliverable: docs\audits\WINDOWS_AUDIT_<yyyy-mm-dd>.md with a one-line verdict, the
environment, a table of every check (pass / fail / evidence), the findings ranked,
what you fixed (with commits), and what needs me. Copy the screenshots it cites into
docs\audits\<yyyy-mm-dd>\ and commit the report and those images. Keep the report as
long as the findings need and no longer.

While working, update me only when you find something important or change course.
Your final message leads with the verdict, then what needs me, in under 200 words.
```

## What the session will use

| File | What it does |
|---|---|
| `scripts/check_workbench.py` | every function, end to end, on the real recording, in a throwaway copy |
| `scripts/visual_audit.py` | every screen rendered at four sizes into a gallery |
| `scripts/unit_page.py` | every unit's real plots in one browser page (`v` on 4 Judge opens it) |
| `scripts/windows/terminal_screenshots.ps1` | the app in a real Windows terminal window, one PNG per screen |
| `.claude/skills/run-spikeinterface/verify_launch.py` | the app launched exactly as a real start |
| `docs/WINDOWS_TEST.md` | the checklist a person would follow |
| `goals/GOAL_V2.md` | the spec being audited |
