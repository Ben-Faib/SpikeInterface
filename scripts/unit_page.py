#!/usr/bin/env python
"""The units page: every unit of a saved sort as a card of real plots, one page.

    uv run python scripts/unit_page.py --sorter tridesclous2          # the current run
    uv run python scripts/unit_page.py --sorter tridesclous2 --run ID
    uv run python scripts/unit_page.py --sorter tridesclous2 --open 16  # build, open at unit 16

The terminal's 4 Judge pane draws each unit in character cells - enough to see
that a spike is there, far too coarse to judge it by. This page is where the unit
is judged by eye: for every unit of the run's RAW sort (the ids 4 Judge labels),

  * spikes on contacts - 40 of the stored spikes, thin, over the template, on the
    peak contact and its neighbours (probe order), one µV scale: spread,
    overlapping shapes and a second waveform family show here, not in a template;
  * autocorrelogram - with the refractory window shaded: a clean unit leaves it
    empty; a merged pair fills it;
  * time between spikes - the ISI histogram, same window, with the count the
    quality metrics were computed from;
  * amplitude over the recording - every spike's amplitude against time, with its
    distribution beside it: drift, a dropout, or two amplitude bands (two cells);
  * features - PC1 against PC2 on the peak contact, this unit against its most
    similar unit: two clouds that touch are the merge / split question;
  * most similar units - template similarity, and the cross-correlogram with the
    closest one.

Flagged units (the merge advisory, "likely two cells") come first, then the rest
in the rollup's strong-first order - the same queue 4 Judge shows, from the same
rollup (sort_summary), with the same verdict words. Labels are NOT drawn here:
labelling happens in the terminal, so this page is never out of date for its run.

Reads only the saved SortingAnalyzer (its waveforms, templates, correlograms,
isi_histograms, spike_amplitudes, principal_components and template_similarity
extensions; each missing one degrades to a note on the card). Writes ONE file,
``units.html`` inside the run directory it describes (``runs.sort_paths``), so a
new sort gets its own page and an old page can never describe a newer run.
Self-contained: Plotly is inlined, it opens offline. Plots draw as they scroll
into view, so a 20-unit page stays quick.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import runs  # noqa: E402
import sort_summary  # noqa: E402

PAGE_NAME = "units.html"
N_SPIKES = 40            # spikes drawn per contact
NEIGHBOURS = 2           # contacts each side of the peak
MAX_SCATTER = 4000       # amplitude points per unit (evenly thinned beyond)
ISI_MAX_MS = 50.0


def page_path(sorter: str, run=None) -> Path:
    """Where the units page of ``sorter``'s run lives (inside that run's folder)."""
    return runs.sort_paths(sorter, run=run)["out"] / PAGE_NAME


def open_at(page: Path, unit) -> Path:
    """A one-line redirect page to ``page#unit-<id>``: file URLs lose their
    #fragment when handed to the OS on Windows, so the app opens this instead."""
    target = page.parent / "units_open.html"
    frag = f"#unit-{unit}" if unit is not None else ""
    target.write_text(
        '<!doctype html><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0;url={PAGE_NAME}{frag}">'
        f'<a href="{PAGE_NAME}{frag}">open the units page</a>', encoding="utf-8")
    return target


# --------------------------------------------------------------------------- #
# Data (all from the saved analyzer)
# --------------------------------------------------------------------------- #
def _ext(analyzer, name):
    try:
        return analyzer.get_extension(name)
    except Exception:  # noqa: BLE001 - a missing/unreadable extension is a note
        return None


def _channel_order(analyzer) -> list:
    """Channel indices ordered along the probe (by y, then x) - the order a
    researcher reads the shank in. Channel order when there is no geometry."""
    try:
        locs = analyzer.get_channel_locations()
        return sorted(range(len(locs)), key=lambda i: (float(locs[i][1]), float(locs[i][0])))
    except Exception:  # noqa: BLE001
        return list(range(analyzer.get_num_channels()))


def _thin(values, limit):
    n = len(values)
    if n <= limit:
        return list(range(n))
    step = n / limit
    return [int(i * step) for i in range(limit)]


def unit_data(analyzer, unit_id, *, order, similar, refractory_ms) -> dict:
    """Everything one card plots, as plain lists (µV where amplitudes)."""
    import numpy as np

    ids = list(analyzer.unit_ids)
    ui = ids.index(unit_id)
    fs = float(analyzer.sampling_frequency)
    chan_ids = [str(c) for c in analyzer.channel_ids]
    out = {"unit": str(unit_id), "notes": []}

    tmpl_ext = _ext(analyzer, "templates")
    wf_ext = _ext(analyzer, "waveforms")
    if tmpl_ext is not None:
        tmpl = np.asarray(tmpl_ext.get_unit_template(unit_id, operator="average"))
        peak = int(np.argmax(np.ptp(tmpl, axis=0)))
        pos = order.index(peak)
        shown = order[max(0, pos - NEIGHBOURS): pos + NEIGHBOURS + 1]
        nbefore = int(tmpl_ext.nbefore)
        t_ms = [round((i - nbefore) / fs * 1000.0, 3) for i in range(tmpl.shape[0])]
        spikes = None
        if wf_ext is not None:
            wf = np.asarray(wf_ext.get_waveforms_one_unit(unit_id, force_dense=True))
            spikes = wf[_thin(wf, N_SPIKES)]
        out["waves"] = {
            "t_ms": t_ms, "peak": chan_ids[peak],
            "channels": [chan_ids[c] for c in shown],
            "template": {chan_ids[c]: np.round(tmpl[:, c], 2).tolist() for c in shown},
            "spikes": ({chan_ids[c]: np.round(spikes[:, :, c], 1).tolist() for c in shown}
                       if spikes is not None else None),
        }
        if spikes is None:
            out["notes"].append("the stored spikes (waveforms extension) are missing")
    else:
        out["notes"].append("no templates saved: no waveform plot")

    cg = _ext(analyzer, "correlograms")
    if cg is not None:
        ccgs, bins = cg.get_data()
        centers = ((np.asarray(bins[:-1]) + np.asarray(bins[1:])) / 2.0).tolist()
        out["acg"] = {"t_ms": [round(c, 3) for c in centers], "n": ccgs[ui, ui].tolist()}
        if similar:
            j = ids.index(similar[0][0])
            out["ccg"] = {"with": str(similar[0][0]), "t_ms": out["acg"]["t_ms"],
                          "n": ccgs[ui, j].tolist()}
    else:
        out["notes"].append("no correlograms saved")

    st = analyzer.sorting.get_unit_spike_train(unit_id, segment_index=0)
    isi = np.diff(st) / fs * 1000.0
    edges = np.arange(0.0, ISI_MAX_MS + 0.5, 0.5)
    counts, _ = np.histogram(isi, bins=edges)
    out["isi"] = {"t_ms": ((edges[:-1] + edges[1:]) / 2).round(3).tolist(),
                  "n": counts.tolist(), "refractory_ms": refractory_ms,
                  "inside": int((isi < refractory_ms).sum()), "n_spikes": int(len(st))}

    amp = _ext(analyzer, "spike_amplitudes")
    if amp is not None:
        try:
            a = np.asarray(amp.get_data(outputs="by_unit")[0][unit_id], dtype=float)
            keep = _thin(a, MAX_SCATTER)
            out["amp"] = {"t_s": np.round(st[keep] / fs, 3).tolist(),
                          "uv": np.round(a[keep], 1).tolist()}
        except Exception as e:  # noqa: BLE001
            out["notes"].append(f"amplitudes unreadable: {e}")
    else:
        out["notes"].append("no spike amplitudes saved")

    pc = _ext(analyzer, "principal_components")
    if pc is not None and "waves" in out:
        try:
            ch = chan_ids.index(out["waves"]["peak"])

            def cloud(u):
                p = np.asarray(pc.get_projections_one_unit(u, sparse=False))
                p = p[_thin(p, 500)]
                return {"pc1": np.round(p[:, 0, ch], 2).tolist(),
                        "pc2": np.round(p[:, 1, ch], 2).tolist()}

            out["pcs"] = {"self": cloud(unit_id), "channel": out["waves"]["peak"]}
            if similar:
                out["pcs"]["other"] = cloud(similar[0][0])
                out["pcs"]["other_id"] = str(similar[0][0])
        except Exception as e:  # noqa: BLE001
            out["notes"].append(f"features unreadable: {e}")
    out["similar"] = [{"unit": str(u), "similarity": round(float(s), 3)} for u, s in similar]
    return out


def _similar(analyzer, top: int = 3) -> dict:
    """{unit: [(other unit, similarity), ...]} - the template_similarity extension."""
    ts = _ext(analyzer, "template_similarity")
    ids = list(analyzer.unit_ids)
    if ts is None:
        return {u: [] for u in ids}
    import numpy as np

    sim = np.asarray(ts.get_data())
    out = {}
    for i, u in enumerate(ids):
        order = [j for j in np.argsort(-sim[i]) if j != i][:top]
        out[u] = [(ids[j], sim[i, j]) for j in order]
    return out


# --------------------------------------------------------------------------- #
# Figures (Plotly, the report's one chart theme)
# --------------------------------------------------------------------------- #
def figures(d: dict, colors: dict) -> list:
    """[(title, plotly figure dict)] for one unit's card."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    import report

    ink, accent, other, warn = colors["ink"], colors["accent"], colors["other"], colors["warn"]
    figs = []

    def style(fig, height):
        fig.update_layout(template=report.CHART_TEMPLATE, height=height,
                          margin=dict(t=30, b=42, l=54, r=14), showlegend=False)
        return fig

    w = d.get("waves")
    if w:
        chans = w["channels"]
        fig = make_subplots(rows=1, cols=len(chans), shared_yaxes=True,
                            subplot_titles=[("contact " + c + (" · peak" if c == w["peak"] else ""))
                                            for c in chans], horizontal_spacing=0.02)
        for k, c in enumerate(chans, 1):
            for s in (w["spikes"] or {}).get(c, []):
                fig.add_trace(go.Scatter(x=w["t_ms"], y=s, mode="lines", hoverinfo="skip",
                                         line=dict(width=0.8, color=accent), opacity=0.16),
                              row=1, col=k)
            fig.add_trace(go.Scatter(x=w["t_ms"], y=w["template"][c], mode="lines",
                                     name="template", line=dict(width=2.4, color=ink)),
                          row=1, col=k)
            fig.update_xaxes(title_text="ms" if k == (len(chans) + 1) // 2 else None, row=1, col=k)
        fig.update_yaxes(title_text="µV", row=1, col=1)
        figs.append(("Spikes on contacts (40 stored spikes over the template)", style(fig, 300)))

    rms = d["isi"]["refractory_ms"]
    if d.get("acg"):
        fig = go.Figure(go.Bar(x=d["acg"]["t_ms"], y=d["acg"]["n"], marker_color=accent,
                               marker_line_width=0))
        fig.add_vrect(x0=-rms, x1=rms, fillcolor=warn, opacity=0.18, line_width=0)
        fig.update_xaxes(title_text="lag (ms)")
        fig.update_yaxes(title_text="spike pairs")
        figs.append((f"Autocorrelogram (shaded: ±{rms:g} ms refractory window)", style(fig, 240)))

    isi = d["isi"]
    fig = go.Figure(go.Bar(x=isi["t_ms"], y=isi["n"], marker_color=accent, marker_line_width=0))
    fig.add_vrect(x0=0, x1=rms, fillcolor=warn, opacity=0.18, line_width=0)
    fig.update_xaxes(title_text="time between spikes (ms)", range=[0, ISI_MAX_MS])
    fig.update_yaxes(title_text="intervals")
    figs.append((f"Time between spikes: {isi['inside']:,} of {max(0, isi['n_spikes'] - 1):,} "
                 f"intervals inside {rms:g} ms", style(fig, 240)))

    a = d.get("amp")
    if a:
        fig = make_subplots(rows=1, cols=2, shared_yaxes=True, column_widths=[0.8, 0.2],
                            horizontal_spacing=0.02)
        fig.add_trace(go.Scattergl(x=a["t_s"], y=a["uv"], mode="markers",
                                   marker=dict(size=3, color=accent, opacity=0.45)), row=1, col=1)
        fig.add_trace(go.Histogram(y=a["uv"], nbinsy=60, marker_color=accent,
                                   marker_line_width=0), row=1, col=2)
        fig.update_xaxes(title_text="time in the recording (s)", row=1, col=1)
        fig.update_xaxes(title_text="spikes", row=1, col=2)
        fig.update_yaxes(title_text="amplitude (µV)", row=1, col=1)
        figs.append(("Amplitude over the recording, and its distribution", style(fig, 280)))

    p = d.get("pcs")
    if p:
        fig = go.Figure()
        if p.get("other"):
            fig.add_trace(go.Scattergl(x=p["other"]["pc1"], y=p["other"]["pc2"], mode="markers",
                                       name=f"unit {p['other_id']}",
                                       marker=dict(size=4, color=other, opacity=0.5)))
        fig.add_trace(go.Scattergl(x=p["self"]["pc1"], y=p["self"]["pc2"], mode="markers",
                                   name=f"unit {d['unit']}",
                                   marker=dict(size=4, color=accent, opacity=0.6)))
        fig.update_layout(showlegend=True)
        fig.update_xaxes(title_text="PC1")
        fig.update_yaxes(title_text="PC2")
        title = f"Features on contact {p['channel']}" + (
            f": unit {d['unit']} against its most similar, unit {p['other_id']}"
            if p.get("other") else "")
        figs.append((title, style(fig, 300).update_layout(showlegend=True)))

    c = d.get("ccg")
    if c:
        fig = go.Figure(go.Bar(x=c["t_ms"], y=c["n"], marker_color=other, marker_line_width=0))
        fig.add_vrect(x0=-rms, x1=rms, fillcolor=warn, opacity=0.18, line_width=0)
        fig.update_xaxes(title_text="lag (ms)")
        fig.update_yaxes(title_text="spike pairs")
        figs.append((f"Cross-correlogram with unit {c['with']} (a dip at 0 = two cells "
                     "that avoid each other; a peak = possibly one cell split in two)",
                     style(fig, 240)))
    return figs


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #
def build(sorter: str, run=None, out_path=None) -> Path:
    import plotly.io as pio
    import spikeinterface.full as si
    from plotly.offline import get_plotlyjs

    import report
    import viz_palette as vp

    paths = runs.sort_paths(sorter, run=run)
    analyzer = si.load_sorting_analyzer(paths["analyzer"])
    summary = sort_summary.load_summary(paths["out"]) or {}
    rollup = (sort_summary.unit_rollup(summary, sort_summary.load_quality_metrics(paths["out"]),
                                       rule=sort_summary.load_quality_rule(
                                           bio.REPO_ROOT / ".si_menu.json"))
              if summary else None)
    rows = {str(r["unit"]): r for r in (rollup or {}).get("units", [])}
    ids = list(analyzer.unit_ids)
    ordered = ([u for u in ids if rows.get(str(u), {}).get("split_advice")]
               + [u for u in ids if not rows.get(str(u), {}).get("split_advice")])
    if rows:   # the rest in the rollup's strong-first order, as 4 Judge shows them
        rank = {k: i for i, k in enumerate(rows)}
        ordered = sorted(ordered, key=lambda u: (0 if rows.get(str(u), {}).get("split_advice")
                                                 else 1, rank.get(str(u), 10 ** 6)))
    order = _channel_order(analyzer)
    similar = _similar(analyzer)
    rms = report._refractory_ms(analyzer)
    ink = vp.CHROME_LIGHT
    colors = {"ink": ink["ink"], "accent": vp.CATEGORICAL_LIGHT[0],
              "other": vp.CATEGORICAL_LIGHT[1], "warn": vp.STATUS["warning"]}
    info = runs.read_json(paths["run_info"])

    nav, cards, data_js = [], [], {}
    for u in ordered:
        r = rows.get(str(u), {})
        d = unit_data(analyzer, u, order=order, similar=similar.get(u, []), refractory_ms=rms)
        figs = figures(d, colors)
        uid = html.escape(str(u))
        flag = bool(r.get("split_advice"))
        nav.append(f'<a href="#unit-{uid}" class="{"flag" if flag else ""}">'
                   f'<b>u{uid}</b><span>ch {html.escape(str(r.get("contact", "?")))}</span>'
                   f'{"<i>two cells?</i>" if flag else ""}</a>')
        bits = [f"contact {r.get('contact', '?')}",
                f"{r.get('n_spikes'):,} spikes" if isinstance(r.get("n_spikes"), int) else None,
                f"{r['v_pp_uV']:.1f} µV p-p" if isinstance(r.get("v_pp_uV"), (int, float)) else None,
                f"SNR {r['snr']:.2f}" if isinstance(r.get("snr"), (int, float)) else None]
        sim = " · ".join(f"u{s['unit']} {s['similarity']:.2f}" for s in d["similar"])
        head = (f'<h2>Unit {uid}</h2><p class="facts">'
                + " · ".join(html.escape(b) for b in bits if b) + "</p>"
                + (f'<p class="verdict">quality rule: {html.escape(r.get("verdict_word", ""))}'
                   + (f' · isolation: {html.escape(r["isolation"])}' if r.get("isolation") else "")
                   + "</p>" if r else "")
                + (f'<p class="advice">{html.escape(r["split_advice"])}</p>' if flag else "")
                + (f'<p class="sim">most similar templates: {html.escape(sim)}</p>' if sim else "")
                + "".join(f'<p class="note">{html.escape(n)}</p>' for n in d["notes"]))
        # Each plot reserves its final height before it draws, so jumping to a unit
        # lands on its card and stays there while the plots fill in.
        plots = "".join(f'<figure><figcaption>{html.escape(t)}</figcaption>'
                        f'<div class="plot" style="height:{int(f.layout.height or 260)}px" '
                        f'data-fig="{uid}:{i}"></div></figure>'
                        for i, (t, f) in enumerate(figs))
        cards.append(f'<section class="card" id="unit-{uid}" data-unit="{uid}">{head}'
                     f'<div class="plots">{plots}</div></section>')
        data_js[str(u)] = [json.loads(pio.to_json(f)) for _t, f in figs]

    title = f"{sorter} · run {paths['id']}"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Units · {html.escape(title)}</title>
<script>{get_plotlyjs()}</script>
<style>
:root {{ --bg:{ink['page']}; --card:{ink['surface']}; --ink:{ink['ink']}; --muted:{ink['ink_secondary']};
  --line:{ink['gridline']}; --accent:{colors['accent']}; --warn:#9a6400; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif; }}
header {{ padding:18px 24px 10px; border-bottom:1px solid var(--line); background:var(--card);
  position:sticky; top:0; z-index:5; }}
header h1 {{ margin:0; font-size:20px; }} header p {{ margin:4px 0 0; color:var(--muted); font-size:13px; }}
.wrap {{ display:grid; grid-template-columns:170px 1fr; }}
nav {{ position:sticky; top:74px; align-self:start; height:calc(100vh - 74px); overflow:auto;
  padding:12px 8px; border-right:1px solid var(--line); }}
nav a {{ display:grid; grid-template-columns:52px 1fr; gap:2px 6px; padding:6px 8px; border-radius:8px;
  color:var(--ink); text-decoration:none; font-size:14px; }}
nav a span {{ color:var(--muted); }} nav a i {{ grid-column:1/-1; color:var(--warn); font-size:12px; font-style:normal; }}
nav a:hover, nav a.here {{ background:rgba(93,100,202,.12); }}
nav a:focus-visible {{ outline:2px solid var(--accent); }}
main {{ padding:16px 24px 80px; min-width:0; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px;
  margin:0 0 20px; scroll-margin-top:110px; }}
.card h2 {{ margin:0; font-size:19px; }}
.facts, .verdict, .sim, .note {{ margin:2px 0; color:var(--muted); }}
.advice {{ margin:6px 0; color:var(--warn); font-weight:600; }}
.note {{ font-style:italic; }}
.plots {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:14px; margin-top:10px; }}
.plots figure:first-child {{ grid-column:1/-1; }}
figure {{ margin:0; min-width:0; }} figcaption {{ font-size:13px; color:var(--muted); margin:0 0 2px; }}
.plot {{ min-height:200px; }}
@media (max-width:760px) {{ .wrap {{ grid-template-columns:1fr; }} nav {{ display:none; }}
  .plots {{ grid-template-columns:1fr; }} }}
</style></head><body>
<header><h1>Units · {html.escape(title)}</h1>
<p>{len(ordered)} units, flagged first · raw sorter output (the ids 4 Judge labels) ·
{html.escape(str((info.get("recording") or {}).get("base") or ""))} ·
refractory window {rms:g} ms · j / k or the arrow keys move between units</p></header>
<div class="wrap"><nav>{''.join(nav)}</nav><main>{''.join(cards)}</main></div>
<script id="figs" type="application/json">{json.dumps(data_js)}</script>
<script>
var FIGS = JSON.parse(document.getElementById("figs").textContent);
function draw(card) {{
  if (card.dataset.drawn) return; card.dataset.drawn = "1";
  card.querySelectorAll(".plot").forEach(function (el) {{
    var k = el.dataset.fig.split(":"), f = FIGS[k[0]][+k[1]];
    Plotly.newPlot(el, f.data, f.layout, {{responsive:true, displaylogo:false}});
  }});
}}
var io = new IntersectionObserver(function (es) {{
  es.forEach(function (e) {{ if (e.isIntersecting) draw(e.target); }});
}}, {{rootMargin:"600px 0px"}});
var cards = Array.prototype.slice.call(document.querySelectorAll(".card"));
cards.forEach(function (c) {{ io.observe(c); }});
function here() {{
  var id = decodeURIComponent(location.hash.replace("#", ""));
  document.querySelectorAll("nav a").forEach(function (a) {{
    a.classList.toggle("here", a.getAttribute("href") === "#" + id); }});
  var c = document.getElementById(id);
  if (c) {{ draw(c); c.scrollIntoView(); }}
}}
window.addEventListener("hashchange", here); here();
document.addEventListener("keydown", function (ev) {{
  var step = {{j:1, ArrowDown:1, k:-1, ArrowUp:-1}}[ev.key];
  if (!step || ev.metaKey || ev.ctrlKey) return;
  var top = window.scrollY + 90, i = 0;
  cards.forEach(function (c, n) {{ if (c.offsetTop <= top) i = n; }});
  var next = cards[Math.max(0, Math.min(cards.length - 1, i + step))];
  if (next) {{ ev.preventDefault(); location.hash = next.id; }}
}});
</script></body></html>"""
    out = Path(out_path) if out_path else paths["out"] / PAGE_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def main() -> int:
    bio.use_utf8_stdout()
    bio.mute_native_chatter()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sorter", required=True)
    ap.add_argument("--run", default=None, help="run id (default: the current run)")
    ap.add_argument("--out", default=None, help="write here instead of the run folder")
    ap.add_argument("--open", default=None, metavar="UNIT",
                    help="open the page at this unit once built")
    args = ap.parse_args()
    if not runs.sort_paths(args.sorter, run=args.run)["analyzer"].exists():
        print(f"no saved {args.sorter} sort to draw - sort it first")
        return 1
    out = build(args.sorter, run=args.run, out_path=args.out)
    print(f"units page: {out}")
    if args.open is not None:
        import webbrowser

        webbrowser.open(open_at(out, args.open).resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
