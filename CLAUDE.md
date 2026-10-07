# CLAUDE.md

**On Windows, asked to audit Spike 2.0? The task and its scope are in `START_HERE_WINDOWS.md`.**

A SpikeInterface workbench being built into a lab tool for Tracy's UPitt lab: loaders, a sort
pipeline, HTML reports and the Spike 2.0 Textual app, all around one Blackrock/Ripple
recording, `PFCM7_d0ephys_Block2`. Not a package: put `scripts/` on `sys.path` and import the
modules. Raw data is git-ignored, so a fresh clone or a cloud session has no data and cannot sort.

## Read only what the task needs

| When | Read |
|---|---|
| Finding where something lives | `docs/ARCHITECTURE.md` (module map, data, pipeline, app wiring, commands) |
| Editing or reviewing code | `docs/INVARIANTS.md` (the rules that bite), then the module's docstring |
| Product intent and rulings | `NORTHSTAR.md` (wins conflicts) |
| A build run | `LOOPS.md` (gates, review, sealing) → the brief in `goals/` → `ROADMAP.md` (NOW + queue) |
| UI work | `DESIGN_UX.md` (its §1 binds every surface) |
| Where things stand | `SEALS.md`, or the `status` skill |
| Calling anything done | the `verify-spike` skill |
| Launching the app | the `run-spikeinterface` skill (a non-TTY launch builds the report instead) |

## Rules for every session

- **Two facts for judging any result.** The noise floor is ~4 µV for every sorter; ~1 µV means
  the channel gain was applied twice. tridesclous2 is non-deterministic here, so unit counts
  and ids are never stable and never a reproduction criterion.
- **NO EM DASHES (U+2014), anywhere, ever**: code, docs, UI strings, commit messages. Use a
  hyphen, colon, period or middot. Pinned by `tests/test_no_em_dashes.py`.
- **Others edit this repo concurrently.** Re-check `git status`/`git diff` right before
  committing, stage explicit paths (never `git add -A`), and commit their unrelated changes
  separately, before yours.

```bash
uv sync --group dev              # env + pytest (Python 3.12 pinned, not 3.13)
uv run python -m pytest tests/   # the whole suite
```
