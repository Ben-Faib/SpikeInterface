"""The sorter shootout: outputs/sweep.html, one page, one question.

    uv run python scripts/sweep_page.py                       # build + print the path
    uv run python scripts/sweep_page.py --sorters lupin,simple
    uv run python scripts/sweep_page.py --nev PATH --out PATH

The question this recording poses: the hand sort puts TWO units on several
electrodes, and tridesclous2 recovers nearly every spike of every one of them
while merging each electrode's pair into a single unit. Does any other sorter
split them, without a trip through Phy?

Every sorter in the sweep is judged on its RAW saved sort, resolved through the
run store (``runs.sort_paths``), against the manually sorted ``.nev`` reference,
by the one matcher this repo has (``compare.manual_pair_test``). Curated results
are never substituted: the point is to compare sorters, not curation decisions,
so every row is the algorithm's own output and the page says so.

A sorter with no judgeable run is a ROW, never a blank: the store is asked what
it holds and the row states it (no saved run, a run that died before writing its
record, a sort with no units, no reference to judge against). Re-running the
command picks up whatever has landed since.

Self-contained and offline, like report.py: the two figures are inline SVG and
the CSS is inline, so the page has no scripts and no external assets at all.
Every colour comes from ``viz_palette`` (the periwinkle system): status colours
for the pair verdicts (state, always beside the word), the periwinkle ramp for
recovery (magnitude, always beside the number), ink tokens for text. The page is
light-mode by design, because it is also the deck's source material and the deck
is the periwinkle wash.
"""
from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import compare  # noqa: E402  (the one matcher: recovery + the pair test)
import curation  # noqa: E402  (whether a sorter also has a curated result)
import runs  # noqa: E402  (the run store: which saved run is current)
import sort_summary  # noqa: E402  (summary.json + the per-unit metrics the run wrote)
import viz_palette as vp  # noqa: E402  (the one home for chart colour)

OUTPUT_DIR = bio.REPO_ROOT / "outputs"
# The roster the shootout runs over. Fixed rather than "every directory under
# outputs/", so an old 20 s experiment from another session cannot wander into a
# full-recording comparison, and so a sorter that has not been swept yet still
# gets a row that says so.
SWEEP_SORTERS = ("tridesclous2", "spykingcircus2", "lupin", "simple",
                 "mountainsort5", "waveclus")
BASELINE = "tridesclous2"

# Row states. Only "judged" carries numbers; the rest are honest rows.
S_JUDGED = "judged"
S_NO_UNITS = "found nothing"
S_NO_SORT = "no saved sort"
S_NO_RUN = "not yet swept"
S_NO_REFERENCE = "no reference"

# Verdict word + palette role for each pair verdict. Status colour is state,
# never decoration, and never the only carrier: the word is always beside it.
VERDICT_STYLE = {
    compare.PAIR_SPLIT: ("Split", "good"),
    compare.PAIR_MERGED: ("Merged", "warning"),
    compare.PAIR_ONE: ("One of two", "serious"),
    compare.PAIR_NEITHER: ("Neither found", "critical"),
}
# Recovery buckets for the grid: (upper bound, ramp step, light text?).
RECOVERY_BUCKETS = ((0.50, 150, False), (0.80, 250, False), (0.95, 400, False),
                    (0.99, 550, True), (1.01, 700, True))


# --------------------------------------------------------------------------- #
# The judgment: one row per sorter
# --------------------------------------------------------------------------- #
def _isi_ratios(out_dir) -> dict:
    """``{unit id: isi_violations_ratio}`` for a run, from the metrics it wrote.

    ``sort_summary.load_quality_metrics`` is the reader (pure csv, no
    SpikeInterface); a missing value stays None, because quality metrics are
    non-fatal here and "not measured" must never render as a zero.
    """
    return {u: row.get("isi_violations_ratio")
            for u, row in sort_summary.load_quality_metrics(out_dir).items()}


def sorter_row(sorter, *, data_dir=None, nev_path=None,
               delta_ms=compare.ONLINE_DELTA_TIME_MS) -> dict:
    """Everything the page says about one sorter, or the honest reason it cannot.

    The store decides what exists (``runs.resolve`` for the current run,
    ``runs.unfinished_runs`` for a sort that died before writing its record); the
    matcher decides what it means. Never raises: a sorter that cannot be judged
    comes back with a ``status`` other than ``judged`` and a ``note`` saying what
    the store actually holds.
    """
    paths = runs.sort_paths(sorter)
    found = runs.resolve(sorter)
    row = {"sorter": sorter, "status": S_NO_RUN, "note": "", "baseline": sorter == BASELINE,
           "run_id": None, "created": None, "window_s": None, "n_units": None,
           "noise_uV": None, "wall_seconds": None, "docker": False, "smoke": False,
           "si_version": None, "effective": {}, "overrides": {}, "has_curated": False,
           "isi": {}, "pair_test": None, "chain": None}
    if found is None:
        dead = runs.unfinished_runs(sorter)
        if dead:
            row["status"] = S_NO_SORT
            row["note"] = (f"{len(dead)} run director{'ies' if len(dead) > 1 else 'y'} on "
                           f"disk ({dead[0].name}) with no run record: the sort died before "
                           "it could save anything to judge. Its sorter_output is kept.")
        else:
            row["note"] = "no run in the store for this sorter yet."
        return row

    info = found["info"]
    summary = sort_summary.load_summary(paths["out"]) or {}
    params = info.get("params") or {}
    row.update({
        "run_id": found["id"], "created": info.get("created"),
        "window_s": info.get("effective_seconds"), "n_units": info.get("n_units"),
        "noise_uV": (summary.get("noise_floor_uV") or {}).get("median"),
        "wall_seconds": info.get("wall_seconds"), "docker": bool(info.get("docker")),
        "smoke": bool(found["smoke"]), "si_version": info.get("si_version"),
        "effective": params.get("effective") or {}, "overrides": params.get("overrides") or {},
        "has_curated": curation.preferred_analyzer(sorter)[1],
        "isi": _isi_ratios(paths["out"]),
        # The preprocessing every sort of this recording shares, from the record
        # rather than from this module's memory of it: the page states what the
        # runs actually did, and says so only while they agree.
        "chain": (info.get("freq_min"), info.get("freq_max"),
                  (info.get("preprocessing") or {}).get("reference"),
                  info.get("n_dropped_analog"),
                  tuple(sorted(str(c) for c in
                               ((info.get("bad_channels") or {}).get("excluded") or []))),
                  info.get("probe_label") or info.get("probe_id"),
                  len(info.get("channel_ids") or [])),
    })
    if not paths["analyzer"].is_dir():
        row["status"] = S_NO_SORT
        row["note"] = (f"run {found['id']} has a record but no saved analyzer, so there is "
                       "no sort to judge.")
        return row
    if not row["n_units"]:
        row["status"] = S_NO_UNITS
        row["note"] = (f"run {found['id']} finished and found no units at all, so there is "
                       "nothing to recover and no pair to split.")
        return row

    test = compare.manual_pair_test(sorter, data_dir=data_dir, nev_path=nev_path,
                                    delta_ms=delta_ms)
    if test is None:
        row["status"] = S_NO_REFERENCE
        row["note"] = ("the manually sorted .nev reference could not be read, so this sort "
                       "was not judged (the sort itself is fine).")
        return row
    row["status"] = S_JUDGED
    row["pair_test"] = test
    return row


def sweep(sorters=None, *, data_dir=None, nev_path=None,
          delta_ms=compare.ONLINE_DELTA_TIME_MS) -> dict:
    """The whole shootout as data: one row per sorter, plus what they share."""
    names = list(sorters) if sorters else list(SWEEP_SORTERS)
    rows = [sorter_row(n, data_dir=data_dir, nev_path=nev_path, delta_ms=delta_ms)
            for n in names]
    judged = [r for r in rows if r["status"] == S_JUDGED]
    first = judged[0]["pair_test"] if judged else {}
    electrodes = sorted({p["electrode"] for r in judged for p in r["pair_test"]["pairs"]})
    references = []
    for r in judged:
        for ref in r["pair_test"]["by_reference"]:
            if ref["unit"] not in [x["unit"] for x in references]:
                references.append({k: ref[k] for k in
                                   ("unit", "electrode", "slot", "n_reference_spikes")})
    references.sort(key=lambda x: (x["electrode"] or 0, x["slot"] or 0))
    return {"rows": rows, "judged": judged, "electrodes": electrodes,
            "references": references,
            "reference": first.get("reference"), "delta_ms": first.get("delta_ms", delta_ms),
            "split_recovery": first.get("split_recovery", compare.SPLIT_RECOVERY),
            "window_s": first.get("window_s"),
            "built": datetime.now().strftime("%Y-%m-%d %H:%M")}


def verdict(data: dict) -> dict:
    """The honest headline, in plain words, computed from the rows themselves."""
    judged = data["judged"]
    splitters, n_pairs, n_split = [], 0, 0
    for r in judged:
        pairs = r["pair_test"]["pairs"]
        n_pairs += len(pairs)
        got = [p for p in pairs if p["verdict"] == compare.PAIR_SPLIT]
        n_split += len(got)
        if got:
            splitters.append(r["sorter"])
    n_electrodes = len(data["electrodes"])
    if not judged:
        return {"headline": "Nothing to judge yet.",
                "lede": "No sorter in the sweep has a saved sort the reference can be "
                        "matched against. The rows below say what the run store holds.",
                "state": "serious", "splitters": []}
    if splitters:
        names = ", ".join(splitters)
        return {"headline": f"{names} splits the pairs.",
                "lede": f"Of {n_pairs} pair verdicts across {len(judged)} sorters, "
                        f"{n_split} came back split: two distinct units, each carrying one "
                        f"of the electrode's two hand-sorted neurons at "
                        f"{data['split_recovery']:.0%} or better. The matrix below says "
                        "which electrode, which units, and how clean each unit's firing "
                        "intervals are.",
                "state": "good", "splitters": splitters}
    return {"headline": "No sorter splits the pairs.",
            "lede": f"All {len(judged)} sorters were judged on the same {n_electrodes} "
                    f"electrodes that carry two hand-sorted neurons each, {n_pairs} pair "
                    "verdicts in total, and not one of them came back split. Where a sorter "
                    "finds the neurons at all it hands back a single unit carrying both, "
                    "which is exactly what tridesclous2 does. Untangling these pairs stays a "
                    "job for Phy (the export is one key away in the dashboard) or for a GPU "
                    "sorter on the lab's Windows box.",
            "state": "warning", "splitters": []}


# --------------------------------------------------------------------------- #
# Small formatting helpers
# --------------------------------------------------------------------------- #
def _e(text) -> str:
    return html.escape(str(text))


def _pct(value) -> str:
    """A recovery fraction as a percentage; an honest dash when there is none."""
    return "-" if value is None else f"{100.0 * value:.0f}%"


def _unit(value, spec=".2f", suffix="") -> str:
    """One numeric cell, or an honest dash when the run never recorded it."""
    if not isinstance(value, (int, float)):
        return "-"
    return f"{value:{spec}}{suffix}"


def _isi(row, unit) -> "float | None":
    value = row["isi"].get(str(unit))
    return value if isinstance(value, (int, float)) else None


def _isi_text(row, units) -> str:
    """"ISI 1.36" / "ISI 0.80 / 0.92", or the honest reason there is no number."""
    if not units:
        return ""
    values = [_isi(row, u) for u in units]
    if all(v is None for v in values):
        return "ISI not measured"
    return "ISI " + " / ".join("-" if v is None else f"{v:.2f}" for v in values)


def _cell_text(row, pair) -> "tuple[str, str, str]":
    """(verdict word, the evidence in one phrase, the ISI line) for one pair."""
    word, _role = VERDICT_STYLE[pair["verdict"]]
    units = pair["sorter_units"]
    by_ref = {r["unit"]: r for r in row["pair_test"]["by_reference"]}
    if pair["verdict"] == compare.PAIR_SPLIT:
        evidence = "units " + " + ".join(str(u) for u in units)
    elif pair["verdict"] == compare.PAIR_MERGED:
        evidence = f"unit {units[0]} carries both"
    elif pair["verdict"] == compare.PAIR_ONE:
        got = next(u for u in pair["units"] if by_ref[u]["recovered_fully"])
        evidence = f"only {got} found ({_pct(by_ref[got]['recovered'])})"
    else:
        evidence = "best " + " and ".join(_pct(by_ref[u]["recovered"]) for u in pair["units"])
    return word, evidence, _isi_text(row, units)


def _ramp_step(recovered) -> "tuple[str, str]":
    """(fill, text colour) for one recovery cell, from the periwinkle ramp.

    The number is printed in every cell, so the ramp is a second reading of a
    fact the cell already states; the text colour flips to the dark-surface ink
    on the two darkest steps, where the light ink would fall under contrast.
    """
    for bound, step, light_text in RECOVERY_BUCKETS:
        if recovered < bound:
            return vp.RAMP[step], (vp.CHROME_DARK["ink"] if light_text
                                   else vp.CHROME_LIGHT["ink"])
    return vp.RAMP[700], vp.CHROME_DARK["ink"]


# --------------------------------------------------------------------------- #
# The two figures (inline SVG: self-contained, and each stands on its own)
# --------------------------------------------------------------------------- #
def _text(x, y, text, *, size=13, fill=None, weight=None, anchor="start") -> str:
    fill = fill or vp.CHROME_LIGHT["ink"]
    weight = f' font-weight="{weight}"' if weight else ""
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" fill="{fill}"'
            f' text-anchor="{anchor}"{weight}>{_e(text)}</text>')


def pair_matrix_svg(data: dict) -> str:
    """THE key visual: every sorter against every two-neuron electrode.

    Built to stand alone away from this page (it is the shootout slide): it
    carries its own title, the rule it applies, the reference it applies it to,
    and the fact that these are raw sorter outputs.
    """
    ink = vp.CHROME_LIGHT
    rows, electrodes = data["rows"], data["electrodes"]
    pad, label_w, cell_w, cell_h, gap = 26, 214, 216, 78, 10
    top = 150
    width = pad + label_w + len(electrodes) * (cell_w + gap) - gap + pad
    height = top + len(rows) * cell_h + 54
    window = data["window_s"]
    provenance = (f"Reference {data['reference']} · raw sorter output, before any curation"
                  + (f" · the whole {window:.0f} s recording"
                     if isinstance(window, (int, float)) else "")
                  ) if data["reference"] else "Nothing judged yet: no reference to judge on."
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
           f'width="{width}" height="{height}" role="img" '
           f'aria-labelledby="pm-title pm-desc" class="figure">',
           f'<title id="pm-title">Pair test: does any sorter split the two hand-sorted '
           f'neurons on an electrode</title>',
           f'<desc id="pm-desc">One row per sorter, one column per electrode carrying two '
           f'hand-sorted units. Each cell states the verdict in words, the units involved, '
           f'and their ISI violation ratios.</desc>',
           f'<rect width="{width}" height="{height}" fill="{ink["surface"]}"/>',
           _text(pad, 44, "Does any sorter split the pairs?", size=25, weight="600"),
           _text(pad, 70, f"Split = two distinct sorter units, each recovering one of the "
                          f"electrode's two hand-sorted neurons at "
                          f"{data['split_recovery']:.0%} or better.",
                 size=13, fill=ink["ink_secondary"]),
           _text(pad, 89, provenance, size=13, fill=ink["ink_muted"])]

    for j, e in enumerate(electrodes):
        x = pad + label_w + j * (cell_w + gap)
        refs = [r["unit"] for r in data["references"] if r["electrode"] == e]
        out.append(_text(x, top - 28, f"electrode {e}", size=13.5, weight="600"))
        out.append(_text(x, top - 11, " + ".join(refs), size=12, fill=ink["ink_muted"]))

    for i, row in enumerate(rows):
        y = top + i * cell_h
        name = row["sorter"] + (" (baseline)" if row["baseline"] else "")
        out.append(_text(pad, y + 30, name, size=15, weight="600"))
        detail = (f"{row['n_units']} units · {_unit(row['window_s'], '.0f', ' s')}"
                  if row["status"] == S_JUDGED else row["status"])
        out.append(_text(pad, y + 50, detail, size=12, fill=ink["ink_muted"]))
        out.append(f'<line x1="{pad}" y1="{y + cell_h - 6}" x2="{width - pad}" '
                   f'y2="{y + cell_h - 6}" stroke="{ink["gridline"]}"/>')
        pairs = {p["electrode"]: p for p in (row["pair_test"] or {}).get("pairs", [])}
        for j, e in enumerate(electrodes):
            x = pad + label_w + j * (cell_w + gap)
            pair = pairs.get(e)
            if pair is None:
                out.append(_text(x, y + 30, "not judged", size=14,
                                 fill=ink["ink_muted"]))
                continue
            word, evidence, isi = _cell_text(row, pair)
            _label, role = VERDICT_STYLE[pair["verdict"]]
            out.append(f'<circle cx="{x + 7}" cy="{y + 24}" r="7" '
                       f'fill="{vp.STATUS[role]}"/>')
            out.append(_text(x + 22, y + 29, word, size=15, weight="600"))
            out.append(_text(x, y + 49, evidence, size=12.5, fill=ink["ink_secondary"]))
            if isi:
                out.append(_text(x, y + 66, isi, size=12, fill=ink["ink_muted"]))
    out.append(_text(pad, height - 18,
                     "ISI = refractory-period violations ratio for the unit named: a merged "
                     "unit fires at intervals one cell cannot.",
                     size=12, fill=ink["ink_muted"]))
    out.append("</svg>")
    return "".join(out)


def recovery_grid_svg(data: dict) -> str:
    """Recovery per hand-sorted unit, every sorter at once.

    Sequential ramp for magnitude, with the percentage printed in every cell, so
    the colour is a second reading of a number the cell already carries.
    """
    ink = vp.CHROME_LIGHT
    rows = [r for r in data["rows"] if r["status"] == S_JUDGED]
    refs = data["references"]
    pad, label_w, cell_w, cell_h, gap = 26, 176, 86, 44, 6
    top = 104
    width = pad + label_w + len(refs) * (cell_w + gap) - gap + pad
    height = top + len(rows) * (cell_h + gap) + 46
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
           f'width="{width}" height="{height}" role="img" '
           f'aria-labelledby="rg-title rg-desc" class="figure">',
           '<title id="rg-title">Recovery of each hand-sorted unit, per sorter</title>',
           '<desc id="rg-desc">A grid of percentages: how much of each hand-sorted unit\'s '
           'spike train each sorter recovered.</desc>',
           f'<rect width="{width}" height="{height}" fill="{ink["surface"]}"/>',
           _text(pad, 40, "How much of each hand-sorted neuron did it find?",
                 size=21, weight="600"),
           _text(pad, 64, "Percentage of that unit's spikes carried by the sorter's best "
                          f"matching unit, within {data['delta_ms']:g} ms.",
                 size=13, fill=ink["ink_secondary"])]
    for j, ref in enumerate(refs):
        x = pad + label_w + j * (cell_w + gap)
        out.append(_text(x + cell_w / 2, top - 22, ref["unit"], size=12.5, weight="600",
                         anchor="middle"))
        out.append(_text(x + cell_w / 2, top - 8, f"{ref['n_reference_spikes']} spikes",
                         size=11, fill=ink["ink_muted"], anchor="middle"))
    for i, row in enumerate(rows):
        y = top + i * (cell_h + gap)
        out.append(_text(pad, y + cell_h / 2 + 5, row["sorter"], size=13.5, weight="600"))
        by_ref = {r["unit"]: r for r in row["pair_test"]["by_reference"]}
        for j, ref in enumerate(refs):
            x = pad + label_w + j * (cell_w + gap)
            got = by_ref.get(ref["unit"])
            recovered = None if got is None else got["recovered"]
            if recovered is None:
                out.append(f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" '
                           f'rx="6" fill="{ink["page"]}" stroke="{ink["gridline"]}"/>')
                out.append(_text(x + cell_w / 2, y + cell_h / 2 + 5, "-", size=13,
                                 fill=ink["ink_muted"], anchor="middle"))
                continue
            fill, text_fill = _ramp_step(recovered)
            out.append(f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" '
                       f'rx="6" fill="{fill}"/>')
            out.append(_text(x + cell_w / 2, y + cell_h / 2 - 1, _pct(recovered), size=15,
                             weight="600", fill=text_fill, anchor="middle"))
            out.append(_text(x + cell_w / 2, y + cell_h / 2 + 14, f"unit {got['best_unit']}",
                             size=10.5, fill=text_fill, anchor="middle"))
    out.append(_text(pad, height - 16,
                     "Darker means more of the hand-sorted unit was found; the number is the "
                     "fact, the shade is the same fact again.",
                     size=12, fill=ink["ink_muted"]))
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #
_CSS_STATIC = """
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); line-height: 1.62;
       font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial,
                    sans-serif; }
.wrap { max-width: 1040px; margin: 0 auto; padding: 0 24px 96px; }
header.hero { background: var(--wash); border-bottom: 1px solid var(--accent-soft);
              padding: 40px 0 34px; margin-bottom: 30px; }
header.hero .wrap { padding-bottom: 0; }
.eyebrow { font-size: 12.5px; letter-spacing: .1em; text-transform: uppercase;
           color: var(--accent); margin: 0 0 10px; font-weight: 600; }
h1 { font-size: 34px; line-height: 1.2; margin: 0 0 14px; letter-spacing: -.01em; }
.lede { font-size: 16.5px; color: var(--ink-2); margin: 0 0 16px; max-width: 74ch; }
.stamp { font-size: 13px; color: var(--ink-muted); margin: 0; }
nav.jump { display: flex; flex-wrap: wrap; gap: 18px; padding: 14px 0 0;
           border-top: 1px solid var(--line); margin-top: 26px; }
nav.jump a { font-size: 13.5px; color: var(--accent); text-decoration: none; }
nav.jump a:hover { text-decoration: underline; }
a:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
section { margin: 0 0 54px; scroll-margin-top: 20px; }
h2 { font-size: 22px; margin: 0 0 6px; letter-spacing: -.01em; }
h3 { font-size: 15px; margin: 26px 0 6px; }
p { margin: 0 0 12px; max-width: 78ch; }
p.note { font-size: 13.5px; color: var(--ink-muted); }
.figure { display: block; width: 100%; height: auto; background: var(--surface);
          border: 1px solid var(--line); border-radius: 12px; margin: 18px 0 10px; }
.figwrap { overflow-x: auto; }
.badges { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 0 0 18px; padding: 0;
          list-style: none; font-size: 13px; color: var(--ink-2); }
.badges li { display: flex; align-items: center; gap: 7px; }
.dot { width: 11px; height: 11px; border-radius: 50%; display: inline-block; }
.dot.good { background: var(--good); } .dot.warning { background: var(--warning); }
.dot.serious { background: var(--serious); } .dot.critical { background: var(--critical); }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; background: var(--surface);
        border: 1px solid var(--line); border-radius: 10px; }
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line); }
th { font-size: 12px; letter-spacing: .04em; text-transform: uppercase;
     color: var(--ink-muted); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:last-child td { border-bottom: none; }
tr.off td { color: var(--ink-muted); }
.tablewrap { overflow-x: auto; }
details { background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
          padding: 10px 14px; margin: 0 0 10px; }
summary { cursor: pointer; font-size: 14px; font-weight: 600; }
details p { margin: 10px 0 6px; font-size: 13.5px; color: var(--ink-2); }
details table { border: none; margin-top: 8px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
       font-size: 12.5px; background: var(--wash-soft); padding: 1px 5px; border-radius: 4px; }
.callout { background: var(--wash-soft); border-left: 3px solid var(--accent);
           border-radius: 0 8px 8px 0; padding: 12px 16px; margin: 0 0 16px;
           font-size: 14px; color: var(--ink-2); }
footer { color: var(--ink-muted); font-size: 12.5px; border-top: 1px solid var(--line);
         padding-top: 14px; }
"""


def _css() -> str:
    """The page's tokens, all of them from viz_palette (no chart hex lives here)."""
    c = vp.CHROME_LIGHT
    pairs = (("page", c["page"]), ("surface", c["surface"]), ("ink", c["ink"]),
             ("ink-2", c["ink_secondary"]), ("ink-muted", c["ink_muted"]),
             ("line", c["gridline"]), ("accent", vp.RAMP[600]),
             ("accent-soft", vp.RAMP[200]), ("wash", vp.DECK["wash"]),
             ("wash-soft", vp.DECK["wash_soft"]), ("good", vp.STATUS["good"]),
             ("warning", vp.STATUS["warning"]), ("serious", vp.STATUS["serious"]),
             ("critical", vp.STATUS["critical"]))
    body = "".join(f"  --{k}: {v};\n" for k, v in pairs)
    return ":root {\n" + body + "}\n" + _CSS_STATIC


def _legend() -> str:
    items = "".join(f'<li><span class="dot {role}"></span>{_e(word)}</li>'
                    for word, role in VERDICT_STYLE.values())
    return f'<ul class="badges">{items}</ul>'


def _sweep_table(data: dict) -> str:
    head = ('<tr><th>sorter</th><th class="num">units</th>'
            '<th class="num">noise floor</th><th class="num">runtime</th>'
            '<th class="num">window</th><th>ran</th><th>run</th></tr>')
    body = ""
    for row in data["rows"]:
        name = _e(row["sorter"]) + (" <em>(baseline)</em>" if row["baseline"] else "")
        if row["n_units"] is None:
            body += (f'<tr class="off"><td>{name}</td><td colspan="6">'
                     f'{_e(row["status"])}: {_e(row["note"])}</td></tr>')
            continue
        where = "Docker image" if row["docker"] else "installed locally"
        note = "" if row["status"] == S_JUDGED else f' <em>({_e(row["status"])})</em>'
        body += (f'<tr><td>{name}{note}</td>'
                 f'<td class="num">{row["n_units"]}</td>'
                 f'<td class="num">{_unit(row["noise_uV"], ".2f", " µV")}</td>'
                 f'<td class="num">{_unit(row["wall_seconds"], ".0f", " s")}</td>'
                 f'<td class="num">{_unit(row["window_s"], ".0f", " s")}</td>'
                 f'<td>{where}</td><td><code>{_e(row["run_id"])}</code></td></tr>')
    return ('<div class="tablewrap"><table><thead>' + head + '</thead><tbody>'
            + body + '</tbody></table></div>')


def _noise_note(data: dict) -> str:
    values = [r["noise_uV"] for r in data["rows"] if isinstance(r["noise_uV"], (int, float))]
    if not values:
        return ""
    return (f'<p class="note">The noise floor is a property of the <em>recording</em> after '
            f'bandpass and the common median reference, not of the sorter, so it lands at '
            f'roughly 4 µV whoever sorts: {min(values):.2f} to {max(values):.2f} µV across '
            f'these {len(values)} sorts. That is the canary. A column reading about 1 µV '
            f'would mean the µV gain had been applied twice, and every amplitude on this '
            f'page with it.</p>')


def _pair_detail(data: dict) -> str:
    """Per sorter, per electrode: the verdict with the numbers it rests on."""
    head = ('<tr><th>sorter</th><th>electrode</th><th>verdict</th><th>sorter unit(s)</th>'
            '<th class="num">ISI ratio</th><th>recovery of the two units</th></tr>')
    body = ""
    for row in data["judged"]:
        by_ref = {r["unit"]: r for r in row["pair_test"]["by_reference"]}
        for pair in row["pair_test"]["pairs"]:
            word, _evidence, _isi_line = _cell_text(row, pair)
            _label, role = VERDICT_STYLE[pair["verdict"]]
            units = pair["sorter_units"]
            isi = " / ".join(
                ("-" if _isi(row, u) is None else f"{_isi(row, u):.2f}") for u in units) or "-"
            recovered = " · ".join(f"{_e(u)} {_pct(by_ref[u]['recovered'])} "
                                   f"(unit {_e(by_ref[u]['best_unit'])})"
                                   for u in pair["units"])
            body += (f'<tr><td>{_e(row["sorter"])}</td><td>e{pair["electrode"]}</td>'
                     f'<td><span class="dot {role}"></span> {_e(word)}</td>'
                     f'<td>{_e(", ".join(str(u) for u in units)) or "-"}</td>'
                     f'<td class="num">{isi}</td><td>{recovered}</td></tr>')
    return ('<div class="tablewrap"><table><thead>' + head + '</thead><tbody>'
            + body + '</tbody></table></div>')


def _chain_note(data: dict) -> str:
    """The preprocessing the sorters were handed, read back from the records.

    It is stated as shared only while the records agree; if a row was
    preprocessed differently that is named, because then the sorters are not
    being asked the same question.
    """
    chains = {}
    for row in data["rows"]:
        if row["chain"]:
            chains.setdefault(row["chain"], []).append(row["sorter"])
    if not chains:
        return ""

    def _words(chain):
        lo, hi, reference, dropped, bad, probe, n_ch = chain
        return (f"{n_ch} neural channels ({dropped} non-neural aux channels dropped first), "
                f"{_e(probe)} geometry, a {_unit(lo, '.0f')} to {_unit(hi, '.0f')} Hz "
                f"bandpass, {len(bad)} channels excluded as bad, then a "
                f"{_e(reference)} reference")

    if len(chains) == 1:
        return (f'<p>The sorters were all handed the same signal, which is what makes the '
                f'rows comparable: {_words(next(iter(chains)))}.</p>')
    parts = "".join(f'<li>{_e(", ".join(names))}: {_words(chain)}</li>'
                    for chain, names in chains.items())
    return ('<p>These rows were <strong>not</strong> preprocessed identically, so they were '
            f'not asked the same question:</p><ul>{parts}</ul>')


def _params_section(data: dict) -> str:
    """What each run actually asked its sorter, stated rather than assumed."""
    out = ""
    for row in data["rows"]:
        if not row["effective"]:
            out += (f'<details><summary>{_e(row["sorter"])}</summary>'
                    f'<p>No parameter record: {_e(row["note"] or "no run to describe")}</p>'
                    '</details>')
            continue
        overrides = row["overrides"]
        si = row["si_version"] or "the installed SpikeInterface"
        if overrides:
            lede = (f"{len(overrides)} parameter(s) overridden by the workbench; every other "
                    f"value below is {_e(si)}'s default for this sorter.")
        else:
            lede = ("No overrides were passed, so the sorter ran on its own defaults, listed "
                    "in full below.")
        if row["docker"]:
            lede += (f" This sort ran in a Docker image, and nothing was passed into it, so "
                     f"the container's own SpikeInterface supplied the defaults it used. The "
                     f"values below were read on this machine ({_e(si)}): that is what the "
                     f"run record can honestly state, and where the image ships a different "
                     f"SpikeInterface version its defaults are the ones that actually ran.")
        rows_html = ""
        for key in sorted(row["effective"]):
            value = row["effective"][key]
            mark = ' <em>(override)</em>' if key in overrides else ""
            rows_html += (f'<tr><td><code>{_e(key)}</code>{mark}</td>'
                          f'<td>{_e(value)}</td></tr>')
        out += (f'<details><summary>{_e(row["sorter"])} · {len(row["effective"])} parameters'
                f'{" · " + _e(row["run_id"]) if row["run_id"] else ""}</summary>'
                f'<p>{lede}</p><div class="tablewrap"><table><thead><tr><th>parameter</th>'
                f'<th>effective value</th></tr></thead><tbody>{rows_html}</tbody></table>'
                f'</div></details>')
    return out


def _reference_table(data: dict) -> str:
    rows = ""
    for ref in data["references"]:
        rows += (f'<tr><td>{_e(ref["unit"])}</td><td class="num">{ref["electrode"]}</td>'
                 f'<td class="num">{ref["slot"]}</td>'
                 f'<td class="num">{ref["n_reference_spikes"]}</td></tr>')
    return ('<div class="tablewrap"><table><thead><tr><th>hand-sorted unit</th>'
            '<th class="num">electrode</th><th class="num">slot</th>'
            '<th class="num">spikes</th></tr></thead><tbody>' + rows
            + '</tbody></table></div>')


def _curated_note(data: dict) -> str:
    named = [r["sorter"] for r in data["rows"] if r["has_curated"]]
    if not named:
        return ""
    return (f'<p class="note">{_e(", ".join(named))} also has a curated result saved. It is '
            'deliberately not what is judged here: the sweep compares algorithms, so every '
            'row is raw sorter output.</p>')


def _document(data: dict) -> str:
    v = verdict(data)
    reference = data["reference"] or "no reference"
    n_judged = len(data["judged"])
    method = f"""
<p>Every row is judged the same way, on the sort the run store says is current for that
sorter, read straight from its saved analyzer.</p>
<h3>The reference</h3>
<p><code>{_e(reference)}</code>, the hand sort of this recording. A Blackrock unit id is a
per-electrode slot, so <code>ch5#1</code> and <code>ch7#1</code> are different neurons that
happen to share a slot number; only the online-sorted class counts, with the unsorted
threshold crossings (slot 0) and the noise slot (255) left out.</p>
<h3>Recovery</h3>
<p>For each hand-sorted unit, the fraction of <em>its</em> spikes the sorter's best matching
unit also carries, within {data['delta_ms']:g} ms. The window is wide on purpose: the .nev
timestamps threshold crossings while an offline sorter is peak-aligned, and the crossing
leads the peak by about 0.6 ms on this recording, so a narrow window would score genuine
matches as zero. Recovery answers "did it find the neuron the human found", which is a
different question from SpikeInterface's symmetric agreement score: an offline sorter
routinely fires several times the events of a conservative hand selection, which dilutes
agreement while recovery stays honest.</p>
<h3>The pair test</h3>
<p>Three electrodes carry two hand-sorted neurons each. A pair counts as
<strong>split</strong> only when two <em>distinct</em> sorter units each recover one of them
at {data['split_recovery']:.0%} or better; when a single unit recovers both that well it is
<strong>merged</strong>, and it is that one unit that carries two cells. The remaining
verdicts say plainly that only one of the two was found, or neither was.</p>
<h3>What this page does not claim</h3>
<p>The hand sort is a <em>reference, not ground truth</em>: it is one experienced human's
selection, and a low recovery is two methods disagreeing rather than a measured error rate.
Unit counts are informational: tridesclous2 is measured non-deterministic on this recording
(14, 16 and 18 units across identical runs), so no verdict here rests on how many units a
sorter produced. Nothing on this page is a curation decision.</p>
"""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sorter shootout · PFCM7_d0ephys_Block2</title>
<style>{_css()}</style>
</head><body>
<header class="hero"><div class="wrap">
<p class="eyebrow">Sorter shootout · PFCM7_d0ephys_Block2</p>
<h1>{_e(v["headline"])}</h1>
<p class="lede">{_e(v["lede"])}</p>
<p class="stamp">{n_judged} sorter(s) judged against {_e(reference)} · raw sorter output,
before any curation · built {_e(data["built"])}</p>
</div></header>
<div class="wrap">
<nav class="jump" aria-label="Sections">
<a href="#pairs">The pair test</a><a href="#recovery">Recovery</a>
<a href="#sweep">The sweep</a><a href="#params">Parameters</a>
<a href="#method">How this was judged</a>
</nav>
<main>
<section id="pairs"><h2>The pair test</h2>
<p>One row per sorter, one column per electrode that the hand sort put two neurons on.</p>
{_legend()}
<div class="figwrap">{pair_matrix_svg(data)}</div>
{_pair_detail(data)}
<p class="note">A high ISI violations ratio beside a merged unit is the evidence that it is
two cells: one neuron cannot fire twice inside its own refractory period, so a unit that
does is firing at intervals a single cell cannot.</p>
</section>

<section id="recovery"><h2>Recovery, per hand-sorted unit</h2>
<p>Before asking whether a sorter separates two neurons, ask whether it found them.</p>
<div class="figwrap">{recovery_grid_svg(data)}</div>
<h3>The hand-sorted units</h3>
{_reference_table(data)}
</section>

<section id="sweep"><h2>The sweep</h2>
<p>Every sorter in the roster, with the run each number came from.</p>
{_sweep_table(data)}
{_noise_note(data)}
{_curated_note(data)}
</section>

<section id="params"><h2>The parameters each run actually used</h2>
<p>Read from each run's own record, not from the current settings: these are the values that
produced the numbers above. They are the <em>sorter's</em> own knobs; the workbench's
preprocessing runs before the sorter sees anything.</p>
{_chain_note(data)}
{_params_section(data)}
</section>

<section id="method"><h2>How this was judged</h2>
{method}
</section>
</main>
<footer>Self-contained: no scripts, no external assets, works offline. Rebuild with
<code>uv run python scripts/sweep_page.py</code>.</footer>
</div>
</body></html>"""


def build_page(out_path=None, sorters=None, *, data_dir=None, nev_path=None,
               delta_ms=compare.ONLINE_DELTA_TIME_MS, data=None) -> Path:
    """Build outputs/sweep.html and return its path."""
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "sweep.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if data is None:
        data = sweep(sorters, data_dir=data_dir, nev_path=nev_path, delta_ms=delta_ms)
    out_path.write_text(_document(data), encoding="utf-8")
    return out_path


def main(argv=None) -> int:
    bio.use_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Build outputs/sweep.html: every swept sorter judged against the "
                    "manually sorted .nev, with the pair test as the verdict.")
    parser.add_argument("--sorters", default=None,
                        help="comma-separated roster (default: "
                             + ", ".join(SWEEP_SORTERS) + ")")
    parser.add_argument("--nev", default=None,
                        help="the sorted .nev reference (default: the derived .nev beside "
                             "the recording)")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--delta-ms", type=float, default=compare.ONLINE_DELTA_TIME_MS,
                        help="coincidence window (default %(default)s ms, wide because "
                             "crossing timestamps lead peak-aligned ones by ~0.6 ms here)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    names = [s.strip() for s in args.sorters.split(",")] if args.sorters else None
    print(build_page(args.out, names, data_dir=args.data_dir, nev_path=args.nev,
                     delta_ms=args.delta_ms))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
