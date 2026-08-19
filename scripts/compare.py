"""Build a standalone interactive comparison of two sorts.

    uv run python scripts/compare.py                        # two saved sorters
    uv run python scripts/compare.py --online tridesclous2  # a sort vs the online .nev units
    uv run python scripts/compare.py --online tridesclous2 --curated \
        --nev PFCM7_d0ephys_Block2_manuallySorted.nev       # the CURATED sort vs a manual .nev

``--curated`` compares the curated sorting (the current run's ``curated/analyzer``,
built by ``curation.py apply``) instead of the raw sorter output — the point of
the curation lifecycle is that decisions can be measured against a reference.
Every page states which of the two it is showing, in both modes; without the flag
a sorter with a curated result is still shown raw, and says so. In the pair mode
each side shows its curated result where it has one and the per-sort note says
which. Asking for ``--curated`` when NO side has one is a hard error, not a
silent fallback to a raw-vs-raw page under a curated flag.

The pair mode writes outputs/comparison.html; the online mode writes
outputs/comparison_online.html — separate files, so building one never silently
replaces the other.

Sorter-vs-sorter (no flags) compares the saved tridesclous2 and spykingcircus2
sorts with SpikeInterface's compare_two_sorters: an agreement-score heatmap + a
matched/unmatched unit table.

IMPORTANT: the comparison is only meaningful if both sorts cover the SAME
recording window. Each sorter's CURRENT run is resolved through the run store
(runs.py) and read from its analyzer — the single source of truth, same as
report.py. If the two durations differ, the page shows a clear caveat instead of
a misleading matrix; re-sort both over a common window first (the
SpikeInterface_Menu.py 'compare' action offers to do this).

``--online <sorter>`` compares that sorter's saved sort against the units the rig
sorted **online**, read from the .nev. Those units are a *reference, not ground
truth*: online sorting is per-channel threshold + template matching, so it
typically undercounts units an offline sorter separates across channels. Only the
online-*sorted* class is used — Blackrock encodes the class in the unit id, and
0 (unsorted threshold crossings) and 255 (noise/invalidated) are dropped with
their spike counts stated on the page. The .nev always spans the whole recording,
so unlike the sorter-vs-sorter mode (which refuses a window mismatch) this mode
crops the reference to the saved sort's window and says so loudly.

``match_manual(sorter, ...)`` is that same machinery returned as DATA rather than
a page — per unit of *our* sort, the reference unit it best matches and how much
of our unit that match accounts for. The report's strong-units block reads it, so
there is still exactly one matcher in this repo. It returns ``None`` whenever the
reference is absent or unusable, so a surface drops the column instead of
guessing at it.
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import curation  # noqa: E402  (curation record + the one output-path resolver; no SI)
import report  # noqa: E402  (reuse the HTML scaffolding helpers)
import runs  # noqa: E402  (the run store: which saved run is current)
import sort_summary  # noqa: E402  (array/yield headline metrics: load/format)

OUTPUT_DIR = bio.REPO_ROOT / "outputs"
DEFAULT_SORTERS = ("tridesclous2", "spykingcircus2")
DELTA_TIME_MS = 0.4   # coincidence window for a "match" (offline vs offline)
# Online/manual .nev references are THRESHOLD-CROSSING timestamped, while offline
# sorters are peak-aligned — a systematic ~0.6 ms lead measured on this recording
# (manual re-export vs tridesclous2: median signed Δt −0.60…−0.67 ms on every real
# pairing). 0.4 ms would score genuine matches as zero agreement, so the online
# mode defaults wider; override with --delta-ms.
ONLINE_DELTA_TIME_MS = 2.0
MATCH_SCORE = 0.5     # min agreement to call two units matched
# Fraction of a REFERENCE unit's spikes our unit must carry before the surfaces
# say it matched it. Symmetric agreement cannot answer that question here: an
# offline sorter routinely fires 5-10x the events of a conservative manual
# selection, so a unit carrying 947 of a reference unit's 959 spikes still scores
# ~0.13 agreement and falls under SI's chance cutoff. Recovery is the direction
# that answers "did we find the neuron the human found?" (face1 review F1).
MATCH_RECOVERY = 0.5
# Two sorts whose durations differ by more than this (seconds) are treated as
# non-commensurate: comparing them would just measure the window mismatch.
DURATION_TOLERANCE_S = 1.0

# --online mode. The Blackrock unit-id classes are a property of the *data*, so
# the class recovery (labels + 0/1..254/255 meaning) lives with the loader:
# bio.online_unit_labels / bio.unit_class / bio.UNIT_CLASS_LABELS.
ONLINE_NAME = "online (.nev)"


def _paths(sorter: str, run=None) -> dict:
    """Every path for ``sorter``'s CURRENT run — the run store is the resolver.

    ``run`` pins a specific run instead: the menu's re-sort-then-compare flow makes
    two ``--duration`` smoke runs, which by design do NOT become current, so the
    page it asked for has to name those runs explicitly or it would compare the
    two sorts the user just replaced.
    """
    return runs.sort_paths(sorter, run=run)


def _analyzer_dir(sorter: str) -> Path:
    """The analyzer of ``sorter``'s CURRENT run — resolved by the run store."""
    return _paths(sorter)["analyzer"]


def saved_sorters() -> list[str]:
    """Sorter names under outputs/ whose current run has a saved analyzer, sorted.

    The store root is read at call time (``runs.outputs_dir``), not from this
    module's import-time OUTPUT_DIR, so the directory scanned and the run resolved
    inside it are always the same tree.
    """
    base = runs.outputs_dir()
    if not base.is_dir():
        return []
    return sorted(
        p.name for p in base.iterdir()
        if p.is_dir() and _analyzer_dir(p.name).exists()
    )


def _load(sorter: str, curated: bool = False, run=None):
    """Return (sorting, duration_s) for the sorter's current run, or (None, None).

    ``curated`` reads that run's ``curated/analyzer`` (the applied curation record)
    instead of the raw sort; both paths come from the run store's ``sort_paths``,
    the one place output paths are resolved. ``run`` pins a run other than the
    current one.
    """
    import spikeinterface.full as si

    paths = _paths(sorter, run)
    analyzer_dir = paths["curated_analyzer"] if curated else paths["analyzer"]
    if not analyzer_dir.is_dir():
        return None, None
    a = si.load_sorting_analyzer(analyzer_dir)
    return a.sorting, float(a.get_total_duration())


def result_line(sorter: str, curated: bool, run=None) -> str:
    """The one honest sentence naming what a page is comparing (curated or raw)."""
    st = curation.state(sorter, run=run)
    record = curation.load_record(path=_paths(sorter, run)["record"])
    return curation.provenance_line(record, curated=curated,
                                    has_curated=st["has_curated"])


def _result_note(sorter: str, curated: bool, run=None) -> str:
    """That sentence as a paragraph, prefixed with the sorter it describes.

    A pinned run is named: the page is then not showing what the pointer says is
    current, and a number nobody can trace back to a run is a number nobody can
    check."""
    where = f' (run {html.escape(str(_paths(sorter, run)["id"]))})' if run else ""
    return (f'<p class="note"><strong>{html.escape(sorter)}{where}:</strong> '
            f'{html.escape(result_line(sorter, curated, run))}.</p>')


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


def _partner_id(v):
    """The matched partner unit id, or None when unmatched.

    The unmatched sentinel varies by SpikeInterface version / dtype: it can be
    "" (empty string, the case in 0.104.3) or -1, and matched partner ids may be
    ints or numeric strings. int()-parsing handles every encoding: "" / None /
    NaN -> unmatched (int() raises), -1 -> unmatched.
    """
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return None
    return None if iv == -1 else iv


def _unmatched(value) -> bool:
    """True when a best-match cell means "no partner reached chance level".

    The sentinel varies by direction and dtype: "" (the 2->1 case in 0.104.3),
    -1, None, or NaN. Everything else IS a partner id — and in the 2->1 direction
    those ids are the REFERENCE's own labels (``ch7#1``), not integers, so they
    must not be int()-parsed away the way :func:`_partner_id` does for 1->2.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False                   # a non-numeric, non-string id is still an id
    return v != v or int(v) == -1      # v != v -> NaN


def _match_table(cmp) -> str:
    hm = cmp.hungarian_match_12  # Hungarian optimal 1:1: sorter1 unit id -> partner unit id
    rows = ""
    n_matched = 0
    for u1, u2 in hm.items():
        p = _partner_id(u2)
        if p is None:
            partner, frac = "—", 0.0
        else:
            partner, frac = str(p), cmp.get_agreement_fraction(u1, u2)
            n_matched += 1
        rows += f"<tr><td>{int(u1)}</td><td>{partner}</td><td>{frac:.3g}</td></tr>"
    n_unmatched = len(hm) - n_matched
    summary = (f'<p class="note">{n_matched} matched · {n_unmatched} unmatched '
               f'{cmp.sorting1_name} units · delta_time={DELTA_TIME_MS} ms · '
               f'match_score={MATCH_SCORE}. {report.SORT_HINT}</p>')
    ths = (report._sort_th(f"{cmp.sorting1_name} unit", 0, True)
           + report._sort_th(f"{cmp.sorting2_name} match", 1)
           + report._sort_th("agreement", 2, True))
    return (summary + '<table class="qc"><thead><tr>' + ths
            + '</tr></thead><tbody>' + rows + '</tbody></table>')


def _metrics_section(curated: bool = False, pinned=None) -> dict:
    """Cross-sorter array/yield table: the six headline metrics for EVERY saved sort.

    Unlike the agreement matrix this is per-sort, so it stays valid even when the
    sorts cover different windows — but unit-count-derived figures (yield, units/ch)
    do scale with window length, so each sort's window is shown for honesty. With
    ``curated`` the curated result's metrics are shown where one exists, and the
    column says so — a curated column must never pass as raw sorter output.
    ``pinned`` maps a sorter to a run other than the current one, so a page built
    against explicit runs does not show the pointer's metrics beside their matrix.
    """
    pinned = pinned or {}
    names = sorted(set(saved_sorters()) | set(pinned))
    cards = []          # (column label, summary card, sorter name, pinned run)
    for n in names:
        run = pinned.get(n)
        paths = _paths(n, run)
        _dir, has_curated = curation.preferred_analyzer(n, run=run)
        use_curated = curated and has_curated
        card = sort_summary.load_summary(paths["curated"] if use_curated else paths["out"])
        cards.append((n + " (curated)" if use_curated else n, card, n, run))
    cards = [c for c in cards if c[1] is not None]
    if not cards:
        body = ('<div class="caveat">No saved array/yield summaries yet — run a sort '
                '(each writes summary.json) to populate this table.</div>')
        return {"id": "metrics", "title": "Array / yield metrics by sorter", "html": body}

    metric_labels = list(sort_summary.headline_row(cards[0][1]).keys())  # the six, in order
    header = "".join(f'<th>{html.escape(lbl)}</th>' for lbl, _c, _n, _r in cards)

    def _row(label, value_of):
        cells = "".join(f"<td>{html.escape(str(value_of(c)))}</td>"
                        for _l, c, _n, _r in cards)
        return f"<tr><td>{html.escape(label)}</td>{cells}</tr>"

    body_rows = _row("units", lambda c: c.get("n_units", 0))
    body_rows += _row("window (s)", lambda c: "—" if c.get("duration_s") is None
                      else f"{c['duration_s']:.0f}")
    # Which saved run each column is. A sorter can have many runs now, so a
    # column without its run id is a number nobody can trace back.
    body_rows += ("<tr><td>run</td>" + "".join(
        f'<td>{html.escape(str(_paths(n, r)["id"] or "—"))}</td>'
        for _l, _c, n, r in cards) + "</tr>")
    for label in metric_labels:
        body_rows += _row(label, lambda c, _l=label: sort_summary.headline_row(c)[_l])

    table = (f'<table class="qc"><thead><tr><th>metric</th>{header}</tr></thead>'
             f'<tbody>{body_rows}</tbody></table>')
    note = ('<p class="note">Headline array/yield metrics for every saved sort. '
            'Amplitudes (V_pp, noise floor) in µV; noise floor is post-CMR (consistent '
            'with SNR). Yield = % of electrodes that are the peak channel of ≥1 unit. '
            'Compare windows before reading unit-count rows across sorters.</p>')
    return {"id": "metrics", "title": "Array / yield metrics by sorter", "html": note + table}


def _pair_names() -> tuple:
    """The two sorters the flagless pair page compares (first two saved sorts)."""
    found = saved_sorters()
    return tuple(found[:2]) if len(found) >= 2 else DEFAULT_SORTERS


def build_comparison(data_dir=None, sorters=None, out_path=None, curated=False,
                     runs_by_sorter=None) -> Path:
    """The two-sorter page. ``runs_by_sorter`` pins one side (or both) to a run
    other than the current one — the menu's re-sort-then-compare flow makes two
    ``--duration`` smoke runs, and a smoke run deliberately never becomes current,
    so the only way to compare what the user just asked for is to name those runs.
    """
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "comparison.html")
    OUTPUT_DIR.mkdir(exist_ok=True)
    pinned = dict(runs_by_sorter or {})
    if sorters is None:
        sorters = _pair_names()
    s1_name, s2_name = sorters

    # With --curated each side shows its curated result where one exists; the
    # per-sort note below says which, so a mixed page is still honest. Whether one
    # exists is the one rule in curation.preferred_analyzer.
    def _side(name):
        run = pinned.get(name)
        _dir, has_curated = curation.preferred_analyzer(name, run=run)
        use = curated and has_curated
        return _load(name, curated=use, run=run), use

    (s1, d1), c1 = _side(s1_name)
    (s2, d2), c2 = _side(s2_name)
    which = (_result_note(s1_name, c1, pinned.get(s1_name))
             + _result_note(s2_name, c2, pinned.get(s2_name)))
    if pinned:
        which = ('<p class="note">This page compares runs named explicitly, not '
                 'whichever run each sorter currently points at — a <code>--duration'
                 '</code> run never displaces a full sort, so the runs just made are '
                 'not current and are named per sorter above.</p>') + which

    if s1 is None or s2 is None:
        missing = [n for n, s in [(s1_name, s1), (s2_name, s2)] if s is None]
        body = ('<div class="caveat">Cannot compare — no saved sort for: '
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

    section = {"id": "compare", "title": f"{s1_name} vs {s2_name}",
               "html": which + body}
    # The cross-sorter array/yield table sits first: it summarises EVERY saved sort
    # (not just the agreement pair) and the six lab-requested metrics live here.
    sections = [_metrics_section(curated=curated, pinned=pinned), section]
    out_path.write_text(report._html_document("Sorter comparison", sections), encoding="utf-8")
    return out_path


# --------------------------------------------------------------------------- #
# --online mode: a saved sort vs the units the rig sorted online (.nev)
# --------------------------------------------------------------------------- #
def _n_spikes(sorting) -> int:
    return sum(len(sorting.get_unit_spike_train(u)) for u in sorting.get_unit_ids())


def split_online_units(sorting, labels):
    """Split a .nev Sorting into its online-*sorted* units and what was dropped.

    Returns ``(sorting_of_sorted_units_or_None, accounting)``. The kept units are
    renamed to their ``ch<n>#<unit>`` labels so every table names the channel the
    online unit came from. ``accounting`` is one row per unit-id class present —
    units, spikes, kept or dropped — so the page can state what it left out
    instead of quietly shrinking n.
    """
    ids = list(sorting.get_unit_ids())
    counts = [len(sorting.get_unit_spike_train(u)) for u in ids]
    classes = [bio.unit_class(label) for label in labels]

    accounting = []
    for key in ("sorted", "unsorted", "noise", "other"):
        idx = [i for i, c in enumerate(classes) if c == key]
        if not idx and key != "sorted":
            continue
        accounting.append({"key": key, "label": bio.UNIT_CLASS_LABELS[key], "n_units": len(idx),
                           "n_spikes": sum(counts[i] for i in idx), "kept": key == "sorted"})

    keep = [i for i, c in enumerate(classes) if c == "sorted"]
    if not keep:
        return None, accounting
    kept = sorting.select_units([ids[i] for i in keep],
                                renamed_unit_ids=[labels[i] for i in keep])
    return kept, accounting


def electrode_breakdown(sorting, labels):
    """One row per .nev spike channel: which electrode, which per-electrode slot.

    A .nev unit id is a per-electrode SLOT, not a global identity — Trellis
    labels each electrode's units independently, so "unit 1" on e5 and "unit 1"
    on e7 are different neurons sharing a slot number. This table is what lets
    the page state the actual number of distinct sorted units (electrode × slot
    combinations) instead of leaving the reader to reconcile slot numbers.
    """
    rows = []
    for u, label in zip(sorting.get_unit_ids(), labels):
        parsed = bio.parse_unit_label(label)
        electrode, slot = parsed if parsed else (None, None)
        cls = bio.unit_class(label)
        rows.append({"electrode": electrode, "slot": slot, "label": label,
                     "class": cls,
                     "n_spikes": len(sorting.get_unit_spike_train(u)),
                     "kept": cls == "sorted"})
    rows.sort(key=lambda r: (r["electrode"] is None, r["electrode"] or 0,
                             r["slot"] or 0))
    return rows


def _span_frames(sorting) -> int:
    """Last spike frame + 1. A bare .nev Sorting has no recording registered, so
    get_total_duration() is unavailable — the spikes themselves are the span."""
    last = 0
    for u in sorting.get_unit_ids():
        train = sorting.get_unit_spike_train(u)
        if len(train):
            last = max(last, int(train[-1]))
    return last + 1


def crop_online(sorting, window_s):
    """Crop the online reference to the saved sort's window.

    The .nev covers the whole recording while a sort may cover only its first
    seconds, so refusing the mismatch (the sorter-vs-sorter rule) would refuse
    every quick sort. Cropping is the honest move — and the crop is stated on the
    page, never silent. Returns ``(sorting, info)``.
    """
    fs = float(sorting.get_sampling_frequency())
    end = int(round(window_s * fs))
    span = _span_frames(sorting)
    before = _n_spikes(sorting)
    info = {"window_s": window_s, "online_span_s": span / fs, "cropped": span > end,
            "n_spikes_before": before, "n_spikes_after": before, "n_empty": 0}
    if info["cropped"]:
        sorting = sorting.frame_slice(start_frame=0, end_frame=end)
        info["n_spikes_after"] = _n_spikes(sorting)
    info["n_empty"] = sum(1 for u in sorting.get_unit_ids()
                          if len(sorting.get_unit_spike_train(u)) == 0)
    return sorting, info


def _crop_note(info) -> str:
    if info["cropped"]:
        note = ('<div class="caveat"><strong>Online reference cropped to the first '
                f'{info["window_s"]:.0f} s to match the sort.</strong> The .nev spans '
                f'{info["online_span_s"]:.0f} s of recording, the saved sort covers '
                f'{info["window_s"]:.0f} s, so the reference drops from '
                f'{info["n_spikes_before"]} to {info["n_spikes_after"]} spikes. Everything '
                'below is that window only.</div>')
    else:
        note = (f'<p class="note">No crop needed — the online units span '
                f'{info["online_span_s"]:.0f} s, inside the sort\'s '
                f'{info["window_s"]:.0f} s window.</p>')
    if info["n_empty"]:
        note += (f'<p class="note">{info["n_empty"]} online unit(s) have no spikes in this '
                 'window; they stay in the matrix as empty rows.</p>')
    return note


def _reference_section(accounting, crop_note="", breakdown=None) -> dict:
    """What the online reference is, and exactly what was left out of it."""
    headline = per_e_table = ""
    kept_rows = [r for r in (breakdown or []) if r["kept"]]
    if kept_rows:
        electrodes = sorted({r["electrode"] for r in kept_rows})
        per_e = ", ".join(
            f"e{e} ×{sum(1 for r in kept_rows if r['electrode'] == e)}"
            for e in electrodes)
        headline = (
            f'<p><strong>This .nev carries {len(kept_rows)} sorted '
            f'unit{"s" if len(kept_rows) != 1 else ""} on {len(electrodes)} '
            f'electrode{"s" if len(electrodes) != 1 else ""}</strong> ({per_e}). '
            'A .nev unit number is a per-electrode slot — Trellis labels each '
            'electrode independently, so "unit 1" on one electrode and "unit 1" '
            'on another are different neurons. The unit count above counts '
            'electrode × slot combinations, which is why it can exceed the '
            'number of unit labels seen in Trellis.</p>')
    if breakdown:
        cells = ""
        for r in breakdown:
            e = f'e{r["electrode"]}' if r["electrode"] is not None else "?"
            slot = ({0: "unsorted (slot 0)", 255: "noise (slot 255)"}
                    .get(r["slot"], f'unit {r["slot"]}')
                    if r["slot"] is not None else "?")
            used = "used here" if r["kept"] else "dropped"
            cells += (f'<tr><td>{e}</td><td>{html.escape(slot)}</td>'
                      f'<td><code>{html.escape(r["label"])}</code></td>'
                      f'<td>{r["n_spikes"]}</td><td>{used}</td></tr>')
        per_e_table = (
            '<table class="qc"><thead><tr><th>electrode</th><th>Trellis label'
            '</th><th>neo name</th><th>spikes</th><th>in this comparison</th>'
            f'</tr></thead><tbody>{cells}</tbody></table>')
    rows = ""
    for c in accounting:
        used = "used here" if c["kept"] else "dropped"
        rows += (f'<tr><td>{html.escape(c["label"])}</td><td>{c["n_units"]}</td>'
                 f'<td>{c["n_spikes"]}</td><td>{used}</td></tr>')
    table = ('<table class="qc"><thead><tr><th>Blackrock unit class</th><th>units</th>'
             f'<th>spikes</th><th>in this comparison</th></tr></thead><tbody>{rows}'
             '</tbody></table>')
    note = ('<p class="note">The .nev carries the rig\'s own sorting, done live during the '
            'recording: per channel, threshold crossings assigned to units by template. '
            'Blackrock puts the class in the unit id — 0 = unsorted threshold crossings, '
            '1–254 = online-sorted, 255 = noise/invalidated — so only the 1–254 class is a '
            'sort at all. The other classes are counted below and left out.</p>')
    n_kept = sum(c["n_units"] for c in accounting if c["kept"])
    return {"id": "online", "title": "The online (.nev) reference",
            "html": headline + per_e_table + note + table + crop_note,
            "state": "ok" if n_kept else "warn"}


def _online_match_table(cmp, online, offline, sorter, delta_ms=ONLINE_DELTA_TIME_MS):
    """Per-online-unit best match. Returns (html, n_at_match_score, n_above_chance).

    Best match, not the Hungarian 1:1 assignment: two online units may point at
    the same offline unit, which is exactly what a channel-local online sort does
    when an offline sorter splits one channel into several units. That is stated
    rather than hidden behind a forced 1:1.
    """
    n_on = {str(u): len(online.get_unit_spike_train(u)) for u in online.get_unit_ids()}
    n_off = {str(u): len(offline.get_unit_spike_train(u)) for u in offline.get_unit_ids()}
    chance = float(cmp.chance_score)

    rows, n_strong, n_any = "", 0, 0
    for u1, u2 in cmp.best_match_12.items():
        partner = _partner_id(u2)
        if partner is None:
            # Below SI's chance cutoff — but "no partner" hides a real structure
            # when the reference unit sits INSIDE a much larger merged unit (the
            # agreement dilution above). Show the best-anything match with its
            # containment, marked below-chance, instead of a shrug.
            best_p, best_frac, matched = None, 0.0, None
            try:
                row = cmp.agreement_scores.loc[u1]
                best_p = row.idxmax()
                best_frac = float(row.max())
                matched = float(cmp.match_event_count.at[u1, best_p])
            except Exception:  # noqa: BLE001 - no scores at all
                best_p = None
            if best_p is not None and best_frac > 0:
                n1 = n_on.get(str(u1), 0) or 1
                contain = f"{min(100.0, 100.0 * (matched or 0) / n1):.0f}%"
                cells = (f"<td>{html.escape(str(best_p))} <span class=\"note\">"
                         f"(below chance)</span></td><td>{best_frac:.3g}</td>"
                         f"<td>{contain}</td>"
                         f"<td>{n_off.get(str(best_p), 0)}</td>")
            else:
                cells = "<td>—</td><td>—</td><td>—</td><td>—</td>"
        else:
            frac = cmp.get_agreement_fraction(u1, u2)
            n_any += 1
            n_strong += frac >= MATCH_SCORE
            # Containment: what fraction of THIS reference unit's spikes the best
            # match accounts for. Symmetric agreement is diluted whenever the
            # offline unit is a MERGE holding many more events (753 fully-matched
            # spikes inside a 5877-spike unit score only 0.13 agreement) — the
            # containment column is what actually answers "did the sorter see
            # this unit's spikes?".
            try:
                matched = float(cmp.match_event_count.at[u1, u2])
            except Exception:  # noqa: BLE001 - matrix indexing differences
                matched = None
            n1 = n_on.get(str(u1), 0) or 1
            # Cap at 100%: with a wide window and a huge partner unit, several
            # offline spikes can coincide with one reference spike and over-count.
            contain = (f"{min(100.0, 100.0 * matched / n1):.0f}%"
                       if matched is not None else "–")
            cells = (f"<td>{html.escape(str(partner))}</td><td>{frac:.3g}</td>"
                     f"<td>{contain}</td>"
                     f"<td>{n_off.get(str(partner), 0)}</td>")
        rows += (f'<tr><td>{html.escape(str(u1))}</td>'
                 f'<td>{n_on.get(str(u1), 0)}</td>{cells}</tr>')

    summary = (f'<p class="note">n = {len(n_on)} online-sorted unit(s). {n_strong} with a best '
               f'match at agreement ≥ {MATCH_SCORE}, {n_any} above chance ({chance:g}); '
               f'a dash means no {html.escape(sorter)} unit reached even chance level. '
               f'delta_time={delta_ms:g} ms (wide on purpose for a crossing-stamped '
               f'reference vs a peak-aligned sort; containment is capped at 100% — '
               f'wide-window multi-coincidences can over-count). '
               f'{report.SORT_HINT}</p>')
    ths = (report._sort_th("online unit (ch#unit)", 0)
           + report._sort_th("online spikes", 1, True)
           + report._sort_th(f"best match in {html.escape(sorter)}", 2)
           + report._sort_th("agreement", 3, True)
           + report._sort_th("of its spikes matched", 4, True)
           + report._sort_th("matched unit spikes", 5, True))
    table = (summary + '<table class="qc"><thead><tr>' + ths
             + '</tr></thead><tbody>' + rows + '</tbody></table>')
    return table, n_strong, n_any


def _online_compare_html(cmp, online, offline, sorter,
                         delta_ms=ONLINE_DELTA_TIME_MS) -> str:
    n_on, n_off = len(online.get_unit_ids()), len(offline.get_unit_ids())
    framing = (f'<p class="note">Agreement between two sorts of the same window — n = {n_on} '
               f'online-sorted unit(s) against {n_off} {html.escape(sorter)} unit(s). The '
               'online units are a <strong>reference, not ground truth</strong>: the rig sorts '
               'one channel at a time from threshold crossings and a template, so it typically '
               'undercounts units an offline sorter separates across channels. Read a low score '
               'as two methods disagreeing, not as an error rate for either — nothing on this '
               'page is accuracy or precision.</p>')
    table, n_strong, n_any = _online_match_table(cmp, online, offline, sorter,
                                                 delta_ms=delta_ms)
    chance = float(cmp.chance_score)
    caveat = ""
    if n_any == 0:
        caveat = ('<div class="caveat"><strong>Zero agreement: no online unit reaches chance '
                  f'level ({chance:g}) against any {html.escape(sorter)} unit.</strong> The '
                  'usual causes are a window mismatch (read the crop note above first), a '
                  'channel mismatch (the sort must cover the channels the online units came '
                  'from), a systematic spike-time offset between online threshold crossings '
                  f'and offline peak-aligned spikes (larger than delta_time = {delta_ms:g} '
                  "ms), or one online unit's spikes spread thin across several offline "
                  'units, so no single pair clears chance even where spikes do coincide. '
                  'The per-unit table below can hint at the last case — an online unit whose '
                  "spike count is far from every offline unit's is consistent with it — but "
                  'similar counts with zero agreement suggest the timing-offset case '
                  'instead.</div>')
    elif n_strong == 0:
        caveat = ('<div class="caveat"><strong>Every best match is below the '
                  f'{MATCH_SCORE} match threshold.</strong> The two sorts overlap but agree on '
                  'no unit. Worth a look at the raw traces before trusting either — start with '
                  'the channels of the online units listed below.</div>')
    return framing + caveat + report._fig_html(_heatmap(cmp)) + table


def match_manual(sorter, data_dir=None, nev_path=None, delta_ms=ONLINE_DELTA_TIME_MS,
                 curated=False, run=None) -> "dict | None":
    """Match a saved sort against a manually sorted ``.nev``, as DATA not HTML.

    The same machinery ``build_online_comparison`` renders — ``split_online_units``
    to keep only the online-*sorted* class, ``crop_online`` to put both sides on
    the same window, and SpikeInterface's ``compare_two_sorters`` — harvested for
    the OTHER direction: for each unit of *our* sort, the reference unit it best
    matches. That is what a per-unit takeaway table needs, and it is why this
    exists instead of a second matcher (there is one matcher, here).

    ``nev_path`` names the reference explicitly; without it the first derived
    ``.nev`` export beside the recording is used (``bio.find_reference_nevs``).

    Returns ``None`` — never a guess — when there is no reference file, no saved
    sort, no readable unit-class labels, or no online-sorted units in the .nev to
    match against. Otherwise::

        {"reference": "PFCM7…_manuallySorted.nev", "delta_ms": 2.0,
         "n_reference_units": 7, "window_s": 132.0, "cropped": False,
         "by_unit": {"4": {"unit": "ch5#2", "recovered": 0.996, "recovers": True,
                           "containment": 0.13, "agreement": 0.13,
                           "n_matched": 750, "n_spikes": 5863,
                           "n_reference_spikes": 753, "below_chance": True}}}

    TWO containments, because they answer different questions and disagree hard
    on this recording:

      ``recovered``    the fraction of the **reference** unit's spikes our unit
                       carries — *did we find the neuron the human found?* This
                       is the headline fact, and ``recovers`` is it against
                       :data:`MATCH_RECOVERY`.
      ``containment``  the fraction of **our** unit's spikes the reference
                       accounts for. Small whenever our unit is the denser of the
                       two, which it usually is.

    Both are capped at 1.0: a wide coincidence window lets several spikes on one
    side coincide with one on the other and over-count. ``below_chance`` is
    SpikeInterface's own symmetric verdict, kept as provenance — it is union
    agreement, which the density asymmetry defeats, so no surface should word a
    match from it.
    """
    if nev_path is None:
        found = bio.find_reference_nevs(data_dir)
        if not found:
            return None
        nev_path = found[0]
    offline, window_s = _load(sorter, curated=curated, run=run)
    if offline is None:
        return None
    try:
        reference = bio.read_spikes(data_dir, nev_path=nev_path)
    except FileNotFoundError:
        return None
    labels = bio.online_unit_labels(reference)
    if labels is None:
        return None
    kept, _accounting = split_online_units(reference, labels)
    if kept is None:
        return None
    cropped, crop_info = crop_online(kept, window_s)

    import spikeinterface.comparison as sc

    cmp = sc.compare_two_sorters(cropped, offline, sorting1_name=ONLINE_NAME,
                                 sorting2_name=sorter, delta_time=delta_ms,
                                 match_score=MATCH_SCORE)
    n_ours = {str(u): len(offline.get_unit_spike_train(u)) for u in offline.get_unit_ids()}
    n_ref = {str(u): len(cropped.get_unit_spike_train(u)) for u in cropped.get_unit_ids()}
    by_unit = {}
    # best_match_21: OUR unit -> the reference unit it best matches. Below SI's
    # chance cutoff it reports no partner; the best-anything row is still the
    # honest answer (an offline unit can sit inside a much larger reference unit),
    # so it is reported and MARKED below chance rather than dropped silently.
    for u2, u1 in cmp.best_match_21.items():
        below = _unmatched(u1)
        partner = u1
        if below:
            try:
                row = cmp.agreement_scores[u2]      # our unit is the COLUMN here
                partner = row.idxmax()
                if not float(row.max()):
                    continue
            except Exception:  # noqa: BLE001 - no scores at all for this unit
                continue
        try:
            agreement = float(cmp.agreement_scores.at[partner, u2])
        except Exception:  # noqa: BLE001 - matrix indexing differences
            agreement = None
        try:
            n_matched = float(cmp.match_event_count.at[partner, u2])
        except Exception:  # noqa: BLE001
            n_matched = None
        mine = n_ours.get(str(u2), 0) or 1
        theirs = n_ref.get(str(partner), 0) or 1
        recovered = None if n_matched is None else min(1.0, n_matched / theirs)
        by_unit[str(u2)] = {
            "unit": str(partner),
            # BOTH directions, because they answer different questions and this
            # recording makes them disagree wildly. `recovered` — how much of the
            # REFERENCE unit we carry — is the one that answers "did we find the
            # human's neuron"; `containment` — how much of OUR unit the reference
            # accounts for — is small whenever our unit is the denser of the two.
            "recovered": recovered,
            "containment": None if n_matched is None else min(1.0, n_matched / mine),
            "recovers": recovered is not None and recovered >= MATCH_RECOVERY,
            "agreement": agreement,
            "n_matched": None if n_matched is None else int(n_matched),
            "n_spikes": n_ours.get(str(u2), 0),
            "n_reference_spikes": n_ref.get(str(partner), 0),
            # SI's own verdict, kept as provenance only. NOTHING should word a
            # cell from it: it is union-agreement, which this asymmetry defeats.
            "below_chance": below,
        }
    return {"reference": Path(nev_path).name, "delta_ms": float(delta_ms),
            "n_reference_units": len(cropped.get_unit_ids()),
            "window_s": window_s, "cropped": bool(crop_info["cropped"]),
            "match_score": MATCH_SCORE, "match_recovery": MATCH_RECOVERY,
            "by_unit": by_unit}


def _caveat_section(sorter, body) -> dict:
    return {"id": "compare", "title": f"{sorter} vs {ONLINE_NAME}",
            "html": f'<div class="caveat">{body}</div>', "state": "warn"}


def build_online_comparison(sorter, data_dir=None, out_path=None, nev_path=None,
                            delta_ms=ONLINE_DELTA_TIME_MS, curated=False) -> Path:
    """outputs/comparison_online.html — one saved sort vs a .nev sorted reference.

    Default reference: the recording's own .nev (the rig's LIVE sorting).
    ``nev_path`` compares against an explicit re-exported .nev instead — e.g. a
    MANUALLY sorted export for the same recording; the page names the file.
    ``curated`` compares the curated sorting instead of the raw one — this is how
    a curation decision is measured against a reference. Which of the two is
    shown is always stated on the page.
    Its OWN file (not the pair page's comparison.html): the two modes must never
    silently replace each other's output (C1 review F2)."""
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "comparison_online.html")
    OUTPUT_DIR.mkdir(exist_ok=True)
    ref_note = (f"Reference: {Path(nev_path).name} (explicit re-export)" if nev_path
                else "The rig's live sorting as a reference")
    which = _result_note(sorter, curated)

    def _write(sections, run_id=None):
        # This page has no array/yield table, so it has no `run` row to carry the
        # id the way the pair page does — it goes in the subtitle instead. Only
        # once a sort is actually loaded: before that there is no run to name.
        where = f" · run {html.escape(str(run_id))}" if run_id else ""
        out_path.write_text(
            report._html_document(f"{sorter} vs sorted .nev units", sections,
                                  subtitle=f"{ref_note}{where} — "
                                           "not ground truth. Self-contained, works offline."),
            encoding="utf-8")
        return out_path

    offline, window_s = _load(sorter, curated=curated)
    # From here on a sort IS loaded, so every exit names which one and repeats the
    # curated-vs-raw sentence. `which` used to be built here and then reach only
    # the fully-compared page: on this recording — which has no online-sorted
    # units — that is the one branch that never runs, so the page said nothing at
    # all about what it had loaded.
    run_id = _paths(sorter)["id"] if offline is not None else None
    if offline is None and curated:
        return _write([_caveat_section(sorter, (
            f'<strong>No curated result for {html.escape(str(sorter))}.</strong> Record '
            'decisions and apply them first: <code>uv run python scripts/curation.py '
            f'apply --sorter {html.escape(str(sorter))}</code>, then rebuild this page.'))])
    if offline is None:
        saved = saved_sorters()
        have = (" Saved sorts: " + ", ".join(saved) + ".") if saved else ""
        return _write([_caveat_section(sorter, (
            f'<strong>No saved sort for {html.escape(str(sorter))}.</strong> Run one first: '
            f'<code>uv run python scripts/run_sorting.py --sorter {html.escape(str(sorter))} '
            f'--duration 30</code>, then rebuild this page.{html.escape(have)}'))])

    try:
        online = bio.read_spikes(data_dir, nev_path=nev_path)
    except FileNotFoundError as e:
        # The loader refuses for two different reasons — nothing to read, or SEVERAL
        # candidate file sets — and only it knows which files it saw. Its own words
        # carry the actionable detail (the candidates by name), so they go on the
        # page verbatim under the general next step.
        return _write([_caveat_section(sorter, (
            which +
            '<strong>No .nev file found.</strong> The online units live in the recording\'s '
            '.nev — put one Blackrock file set (.nev + .ns5) in the repo root and rebuild. '
            'Without it, compare two offline sorters instead: '
            '<code>uv run python scripts/compare.py</code>.'
            f'<p class="note">Loader: {html.escape(str(e))}</p>'))], run_id=run_id)

    labels = bio.online_unit_labels(online)
    if labels is None:
        return _write([_caveat_section(sorter, (
            which +
            '<strong>Could not read the .nev unit-class labels</strong>, so the unsorted '
            '(id 0) and noise (id 255) classes cannot be told apart from the online-sorted '
            'ones. Comparing everything would misstate what the rig sorted, so nothing is '
            'compared here. Compare two offline sorters instead: '
            '<code>uv run python scripts/compare.py</code>.'))], run_id=run_id)

    kept, accounting = split_online_units(online, labels)
    breakdown = electrode_breakdown(online, labels)
    if kept is None:
        dropped = sum(c["n_spikes"] for c in accounting if not c["kept"])
        channels = sum(c["n_units"] for c in accounting if not c["kept"])
        return _write([_reference_section(accounting, breakdown=breakdown),
                       _caveat_section(sorter, (
            which +
            '<strong>This recording has no online-sorted units, so there is nothing to '
            f'compare against.</strong> Its .nev holds {dropped} spikes across {channels} '
            'unit-id-0/255 group(s): the rig detected threshold crossings but never assigned '
            'them to online units. Sort the .nev online in the recording software and '
            're-export, or compare two offline sorters instead: '
            '<code>uv run python scripts/compare.py</code>.'))], run_id=run_id)

    cropped, crop_info = crop_online(kept, window_s)

    import spikeinterface.comparison as sc

    cmp = sc.compare_two_sorters(cropped, offline, sorting1_name=ONLINE_NAME,
                                 sorting2_name=sorter, delta_time=delta_ms,
                                 match_score=MATCH_SCORE)
    return _write([
        _reference_section(accounting, _crop_note(crop_info), breakdown=breakdown),
        {"id": "compare", "title": f"{sorter} vs {ONLINE_NAME}",
         "html": which + _online_compare_html(cmp, cropped, offline, sorter,
                                              delta_ms=delta_ms)},
    ], run_id=run_id)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build outputs/comparison.html: two saved sorts, or one sort "
                    "against the recording's online (.nev) units.")
    parser.add_argument(
        "--online", metavar="SORTER",
        help="compare SORTER's saved sort against the online-sorted .nev units "
             "instead of against a second sorter")
    parser.add_argument(
        "--nev", metavar="PATH", default=None,
        help="with --online: use this explicit .nev as the sorted reference "
             "(e.g. a manually sorted re-export) instead of the recording's own")
    parser.add_argument(
        "--delta-ms", type=float, default=ONLINE_DELTA_TIME_MS,
        help="with --online: the coincidence window (default %(default)s ms — wide "
             "because crossing timestamps lead peak-aligned ones by ~0.6 ms here)")
    parser.add_argument(
        "--curated", action="store_true",
        help="compare the CURATED sorting (outputs/<sorter>/curated/, built by "
             "curation.py apply) instead of the raw sorter output")
    args = parser.parse_args(argv)
    if args.nev and not args.online:
        parser.error("--nev requires --online SORTER")
    # An explicit --curated with nothing applied fails hard rather than quietly
    # comparing the raw sort (the repo's explicit-fails-hard asymmetry). In the
    # pair mode each side may or may not have a curated result — but if NEITHER
    # does, the page would be raw-vs-raw under a --curated flag, so that errors too.
    if args.curated:
        wanted = [args.online] if args.online else list(_pair_names())
        curated_now = [n for n in wanted if curation.preferred_analyzer(n)[1]]
        if not curated_now:
            names = ", ".join(str(n) for n in wanted)
            parser.error(
                f"--curated: no curated result for {names} — record decisions and run: "
                "uv run python scripts/curation.py apply --sorter "
                f"{wanted[0] if wanted else '<sorter>'}")
    print(build_online_comparison(args.online, nev_path=args.nev,
                                  delta_ms=args.delta_ms, curated=args.curated)
          if args.online else build_comparison(curated=args.curated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
