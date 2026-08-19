# Collapsible Docker-download view with live telemetry

**Date:** 2026-06-27
**Status:** Design approved, ready for implementation plan

## Problem

The in-UI Docker-image download (`DownloadProgressScreen` in `scripts/menu_app.py`)
shows only a phase caption ("Downloading 4/7 layers"), a determinate bar + percent,
and a spinner. It tells you *that* it's working but not *how fast* or *how long left*,
and it is a blocking modal - you can't do anything else in the menu while a ~1 GB
image downloads, and there's no compact "keep an eye on it" mode.

## Goals

1. **Richer telemetry** in the full view: downloaded/total size, live download speed,
   ETA, and elapsed time - alongside the existing phase caption + bar + percent.
2. **Collapsible:** dismiss the full modal back to the live dashboard while the
   download keeps running in the background, leaving a compact one-line indicator
   (percent · speed · ETA) under the DATA/SORT banner.
3. **Re-expandable:** re-open the full view at any time while the download is still
   in progress.

## Non-goals (YAGNI)

- **Multiple concurrent downloads.** One image downloads at a time (~1 GB each).
  Starting a second while one is live is refused with a footer hint.
- A download history / log. The indicator clears shortly after completion.
- Progress persistence across app restarts. A download is bound to the running app.

## Key decisions (locked)

- **Collapse target:** back to the dashboard with a compact indicator in the banner
  area (chosen over "stay modal, shrink in place"). This is the more flexible option
  - the menu stays usable while the image downloads.
- **Full view metric set:** full telemetry (downloaded/total, speed, ETA, elapsed),
  not the lean speed+ETA-only variant.
- **Expand key:** `w` (free on the dashboard; the indicator line shows the hint).
- **Speed smoothing:** EMA (exponential moving average) so the number doesn't jitter
  between SDK progress events.

## Architecture

### The enabling change: move the worker from the screen to the App

Today the pull runs in a worker owned by `DownloadProgressScreen`
(`self.run_worker(self._pull, thread=True, exclusive=True)`), so unmounting the modal
cancels the download. To let the download survive a collapse, the worker moves **up to
`SpikeMenuApp`**, which owns a single live `DownloadSession`. The modal becomes a pure
*view* over that session; the dashboard indicator is another view over the same
session. Closing either view never touches the worker.

### `scripts/download_stats.py` - new pure module (no Textual, no Docker)

Mirrors the `scripts/sort_progress.py` pattern: pure, fully unit-testable, holds all
the math so the TUI stays a thin renderer.

- **`DownloadStats`** - fed `(done, total)` byte samples with a monotonic timestamp via
  `update(done, total, now)`. Maintains:
  - `pct` - `int(done/total*100)` (0 when `total==0`).
  - `speed` - EMA-smoothed bytes/second over recent samples (the EMA absorbs the
    bursty per-event deltas). `None`/0 until there's a second sample.
  - `eta` - `(total - done) / speed` seconds, `None` when speed is unknown/0 or
    `total` unknown.
  - `elapsed` - `now - start` seconds.
  - Edge cases handled: `total == 0`, `done > 0` before `total` is known, `done`
    resetting between the download and extract phases (each phase reports its own
    byte totals - `DownloadStats` is told when the phase changes and resets its
    sample window so speed/ETA recompute cleanly rather than going negative).
- **Formatters** (module-level, pure): `fmt_bytes(n)` → `"423 MB"`,
  `fmt_speed(bps)` → `"2.3 MB/s"`, `fmt_clock(secs)` → `"0:38"` / `"1:12"`
  (mm:ss, h:mm:ss when ≥ 1 h). `None` inputs render as `"-"`.
- **`DownloadSession`** dataclass: `name`, `image`, `phase`
  (`"downloading"`/`"verifying"`/`"extracting"`/`"done"`), `stats: DownloadStats`,
  `result: tuple[bool, str] | None`, and a `cancelled: bool` flag.

The phase string from the registry's `on_status` ("Downloading n/N layers",
"Verifying…", "Extracting n/N layers", "Done") maps to the `phase` field; the
`on_progress(done, total)` callback feeds `stats.update(...)`.

### App-level download lifecycle (`SpikeMenuApp`)

- `self._download: DownloadSession | None` - the single live session (None when idle).
- `start_download(name)` - refuse with a footer hint if one is already live
  (`download already running · w to view`). Otherwise build the session, start an
  **App-owned** worker thread running the pull, and push the (view-only)
  `DownloadProgressScreen`. Reached from `_select_sorter` (Docker sorter, image not
  present, daemon running) in place of today's direct screen push.
- `_on_dl_update()` - marshalled from the worker via `call_from_thread`; updates the
  session, then repaints whatever views are live: the modal if mounted, and always
  the `#dlbar` indicator.
- `_on_dl_finish(ok, msg)` - sets `session.result`, runs the existing
  `_after_download` reload (catalog reload → row badge/readiness flip → banner +
  inspect repaint), updates the modal's ✓/✗ line if it's open, and switches the
  `#dlbar` to a transient `✓ <name> ready` / `✗ …` line that clears after a short
  `set_interval`, then sets `self._download = None`.

### The two views

**Expanded - `DownloadProgressScreen` (view-only over the session):**

```
┌─ DOWNLOAD ─────────────────────────┐
│ Downloading tridesclous2           │
│ ⠋ Downloading 4/7 layers           │
│ ███████████░░░░░░░░░░░░  47%        │
│                                     │
│ 423 MB / 900 MB   2.3 MB/s          │
│ ETA 0:38          elapsed 1:12      │
│                                     │
│ This runs once (~1 GB).             │
│ [c] collapse  ·  [Esc] cancel       │
└─────────────────────────────────────┘
```

- No longer owns the worker; it reads `self.app._download` and repaints on a
  `set_interval` tick (also drives the spinner, as today).
- `c` → `action_collapse`: dismiss the modal with a `"collapsed"` sentinel; the worker
  keeps running, the `#dlbar` indicator takes over.
- `Esc` → `action_cancel`: set `session.cancelled = True` (the worker's `should_cancel`
  hook breaks the pull) and dismiss. The catalog reload still runs on finish.
- During the extract/verify phases (no meaningful byte total or speed) the size /
  speed / ETA fields render as `-`; the bar still tracks the extract aggregate and
  elapsed still ticks.

**Collapsed - `#dlbar` Static on the dashboard:**

```
⬇ tridesclous2  47%  2.3 MB/s  ETA 0:38   [w expand]
```

- New `Static(id="dlbar")` placed in `compose()` immediately after `#sortbar`.
- `display:none` (a `hidden` class) whenever `self._download is None` *and* there's no
  transient completion line; shown otherwise. A `_render_dlbar(width)` helper renders
  it; called from `_relayout` and from `_on_dl_update`.
- On completion, shows `✓ tridesclous2 ready` (accent-green) / `✗ …` for a few seconds,
  then hides.
- NO_COLOR-safe shape cues: the `⬇` / `✓` / `✗` glyph + the explicit `%`/`ready` word
  carry meaning without relying on colour, consistent with the DATA/SORT banner style.

**Re-expand:** dashboard binding `w` → `action_watch_download`: if a session is live,
push a fresh `DownloadProgressScreen` re-attached to the existing session. No-op (or a
faint footer hint) when no download is active.

### Registry: make the pull cancellable

`scripts/sorters.pull_docker_image(image, on_progress, on_status, should_cancel=None)`
gains an optional `should_cancel` callable, checked once per streamed event; when it
returns True the loop breaks and the function returns False (treated as an interrupted
download - the row simply stays "not downloaded"). Defaults to `None` (no behaviour
change for existing callers, including `run_sorting.py`).

`MenuController.download_image` gains a matching pass-through `should_cancel` parameter
so the App can thread the session's cancel flag down to the registry.

### Responsive behaviour

`#dlbar` is one row. It follows the banner's collapse tiers but **stays visible while a
download is active** (it's important live feedback) until the most extreme `tiny` tier,
where everything but the lists collapses - the crest and title yield first, as today.
The expanded modal already has `max-height: 90%` + scroll, so the extra two stats rows
fit on short windows.

## Components & boundaries

| Unit | Responsibility | Depends on |
| --- | --- | --- |
| `scripts/download_stats.py` | Pure math + formatting + session dataclass | stdlib only |
| `scripts/sorters.pull_docker_image` | Stream a docker pull; honour `should_cancel` | docker SDK |
| `MenuController.download_image` | Resolve image, pass callbacks + cancel down | sorters |
| `SpikeMenuApp` (download lifecycle) | Own the worker + session; repaint views | download_stats, controller |
| `DownloadProgressScreen` | Render the expanded view; collapse/cancel | session (read-only) |
| `#dlbar` + `_render_dlbar` | Render the collapsed indicator | session (read-only) |

The Textual process still imports **no SpikeInterface and no Docker SDK** - all Docker
work stays in the controller/registry on the worker thread; `download_stats` is pure.

## Error handling

- A worker exception becomes `result = (False, "download failed: …")` (as today),
  surfaced in both views; the session clears and the catalog reload still runs.
- `should_cancel` → clean break, `(False, "download cancelled")`; row unchanged.
- `total == 0` / unknown → percent 0, speed/ETA render `-`; the spinner conveys
  liveness (unchanged from today's indeterminate-stretch handling).
- A reload failure after download is caught and shown, never crashes the app (existing
  `_after_download` behaviour preserved).

## Testing

**Pure unit tests - `tests/test_download_stats.py`:**
- `pct` from `(done, total)`, including `total == 0` → 0.
- EMA `speed` over a scripted sample sequence; `None`/0 before the second sample.
- `eta` = remaining/speed; `None` when speed unknown.
- `elapsed` from injected monotonic timestamps (timestamps passed in - no real clock).
- Phase change resets the sample window so speed never goes negative across the
  download→extract byte-total reset.
- Formatters: `fmt_bytes`, `fmt_speed`, `fmt_clock` (incl. ≥ 1 h), `None` → `"-"`.

**Pilot tests - extend `tests/test_menu_app.py`:**
- A stub controller whose `download_image` drives `on_progress`/`on_status` from a
  scripted sequence (no real Docker), as existing tests stub the controller.
- Start a download on a docker-sorter row → expanded modal shows the stats lines.
- Press `c` → modal closes, `#dlbar` visible with percent + ETA.
- Press `w` → modal re-opens, re-attached to the same live session.
- Finish → `controller.reload` called, row badge/readiness flips, `#dlbar` shows the
  transient ready line then hides.
- Press `Esc` mid-download → `should_cancel` flag set, modal closes.
- Never-clip regression: a download active under a short window keeps the lists
  reachable (re-pin the existing tiny-tier assertions with `#dlbar` shown).

## Out-of-scope follow-ups

- Surfacing the same telemetry in the prompt_toolkit/typed fallback menu - the
  fallback currently has no in-UI download progress and stays as-is.
