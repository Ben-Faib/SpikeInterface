// The lab-meeting deck (GOAL_PRESENT item 8), built LAST from finished pieces.
//
//   ASSET_DIR=/path/to/rendered/assets OUT=/path/to/deck.pptx node make_deck.js
//
// Every number in the speaker notes traces to a surface: outputs/sweep.html
// (the shootout), outputs/report.html (the evidence), SEALS.md (the sealed
// measurements). Slides stay light on text by design (Ben's decision 6): the
// script lives in the notes. Colors come from scripts/viz_palette.py's DECK
// block (periwinkle wash, darker periwinkle accents). No credits anywhere.
//
// Assets expected in ASSET_DIR (rendered per the v4 run; regenerate with the
// capture commands recorded in the seal): tui_dashboard.png, tui_triage.png,
// fig_snr.png, fig_isi.png, fig_pair_matrix.png, fig_recovery_strip.png,
// appendix_report.png, appendix_sweep.png.
const pptxgen = require("pptxgenjs");
const path = require("path");

const A = process.env.ASSET_DIR || ".";
const OUT = process.env.OUT || "lab_meeting_deck.pptx";
const img = (name) => path.join(A, name);

// viz_palette.DECK + friends (hex without '#', per pptxgenjs)
const WASH = "E2E7FC", SOFT = "EFF1FC", WHITE = "FFFFFF";
const ACCENT = "2D2F77", ACCENT_SOFT = "5056B6", PERI = "656DD7";
const INK = "0E0E14", SEC = "504F5C", AMBER = "8A5A00";
const FONT = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5

const shadow = () => ({ type: "outer", color: "2D2F77", opacity: 0.16, blur: 10, offset: 2, angle: 90 });

function slide(notes) {
  const s = pres.addSlide();
  s.background = { color: WASH };
  if (notes) s.addNotes(notes);
  return s;
}
function title(s, text, opts = {}) {
  s.addText(text, Object.assign({ x: 0.7, y: 0.42, w: 11.9, h: 0.85, fontFace: FONT,
    fontSize: 33, bold: true, color: ACCENT, margin: 0 }, opts));
}
function card(s, x, y, w, h) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.09,
    fill: { color: WHITE }, line: { type: "none" }, shadow: shadow() });
}
// The key-chip motif: the same inverse-video key caps the dashboard uses.
function chip(s, x, y, key, size = 0.52) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w: size, h: size, rectRadius: 0.07,
    fill: { color: ACCENT }, line: { type: "none" } });
  s.addText(key, { x, y, w: size, h: size, align: "center", valign: "middle",
    fontFace: "Courier New", fontSize: 17, bold: true, color: WHITE, margin: 0 });
}

// ---- 1 · Title -------------------------------------------------------------
let s = slide(
  "Today: how we go from a raw Blackrock recording to neurons we can defend, on our own machine, in minutes. " +
  "The recording behind every number in this talk is PFCM7 d0ephys Block2: 132 seconds, 16 electrodes, 30 kHz broadband, " +
  "NeuroNexus A1x16 probe at 100 microns. Everything shown is the tool as it runs today.");
title(s, "From raw recording to neurons you can defend", { y: 2.35, w: 7.6, fontSize: 40, h: 2.0 });
s.addText("A spike-sorting workbench on SpikeInterface", { x: 0.7, y: 4.35, w: 7.2, h: 0.5,
  fontFace: FONT, fontSize: 19, color: ACCENT_SOFT, margin: 0 });
s.addText("PFCM7_d0ephys_Block2 · 16 electrodes · 132 s", { x: 0.7, y: 4.85, w: 7.2, h: 0.4,
  fontFace: FONT, fontSize: 13, color: SEC, margin: 0 });
card(s, 8.35, 1.7, 4.35, 4.1);
s.addImage({ path: img("tui_dashboard.png"), x: 8.5, y: 1.85, w: 4.05, h: 2.7 });
s.addText("the whole workflow on one screen", { x: 8.5, y: 4.7, w: 4.05, h: 0.4, align: "center",
  fontFace: FONT, fontSize: 12, italic: true, color: SEC, margin: 0 });

// ---- 2 · The problem -------------------------------------------------------
s = slide(
  "Manual spike sorting is the bottleneck. Hours per recording of clicking through waveforms. " +
  "Two experts sort the same file and disagree, and six months later nobody can say why a unit was accepted. " +
  "For a lab that wants to compare across days and animals, that subjectivity compounds.");
title(s, "Sorting by hand is slow, subjective, and hard to audit");
const probs = [
  ["Hours", "per recording, by hand"],
  ["Two experts,\ntwo answers", "the same file sorts differently"],
  ["No audit trail", "why was this unit accepted?"],
];
probs.forEach(([big, small], i) => {
  const x = 0.7 + i * 4.2;
  card(s, x, 2.1, 3.8, 3.4);
  s.addText(big, { x: x + 0.3, y: 2.6, w: 3.2, h: 1.5, fontFace: FONT, fontSize: 30,
    bold: true, color: ACCENT, margin: 0 });
  s.addText(small, { x: x + 0.3, y: 4.25, w: 3.2, h: 0.9, fontFace: FONT, fontSize: 15,
    color: SEC, margin: 0 });
});

// ---- 3 · SpikeInterface ----------------------------------------------------
s = slide(
  "SpikeInterface is the field's shared standard: one framework that reads our Blackrock files and runs " +
  "essentially every published sorter through one interface, with the same preprocessing. Same data in, any " +
  "algorithm out, and the whole pipeline is scriptable and reproducible. The workbench is a face on top of it: " +
  "nobody in the lab needs to know SpikeInterface, Docker, or quality-metric lore to use it.");
title(s, "SpikeInterface: one standard, many sorters");
card(s, 0.7, 2.3, 3.1, 2.5);
s.addText("Blackrock\n.ns5 / .nev", { x: 0.7, y: 2.3, w: 3.1, h: 2.5, align: "center", valign: "middle",
  fontFace: FONT, fontSize: 19, bold: true, color: INK, margin: 0 });
s.addShape(pres.ShapeType.rightArrow, { x: 3.95, y: 3.3, w: 0.85, h: 0.5, fill: { color: ACCENT_SOFT }, line: { type: "none" } });
s.addShape(pres.ShapeType.roundRect, { x: 4.95, y: 2.3, w: 3.4, h: 2.5, rectRadius: 0.09,
  fill: { color: ACCENT }, line: { type: "none" }, shadow: shadow() });
s.addText("SpikeInterface", { x: 4.95, y: 2.3, w: 3.4, h: 2.0, align: "center", valign: "middle",
  fontFace: FONT, fontSize: 21, bold: true, color: WHITE, margin: 0 });
s.addText("load · filter · reference · sort · measure", { x: 4.95, y: 4.1, w: 3.4, h: 0.5, align: "center",
  fontFace: FONT, fontSize: 11.5, color: WASH, margin: 0 });
s.addShape(pres.ShapeType.rightArrow, { x: 8.5, y: 3.3, w: 0.85, h: 0.5, fill: { color: ACCENT_SOFT }, line: { type: "none" } });
["tridesclous2", "spykingcircus2", "mountainsort5", "waveclus · lupin · …", "kilosort4 (GPU)"].forEach((name, i) => {
  s.addShape(pres.ShapeType.roundRect, { x: 9.6, y: 1.95 + i * 0.72, w: 3.0, h: 0.56, rectRadius: 0.07,
    fill: { color: i === 0 ? PERI : SOFT }, line: { type: "none" } });
  s.addText(name, { x: 9.75, y: 1.95 + i * 0.72, w: 2.8, h: 0.56, valign: "middle",
    fontFace: FONT, fontSize: 13.5, bold: i === 0, color: i === 0 ? WHITE : INK, margin: 0 });
});
s.addText("same recording, any algorithm - and every run reproducible", { x: 0.7, y: 5.6, w: 11.9, h: 0.5,
  fontFace: FONT, fontSize: 15, italic: true, color: SEC, margin: 0 });

// ---- 4 · The workbench -----------------------------------------------------
s = slide(
  "The workbench puts the whole workflow on one screen, in three stages. Get data: files, probe geometry, a look at the raw signal. " +
  "Sort and curate: pick a sorter, sort, judge every unit, export the hard cases to Phy. Look and share: the report, the GUI, comparisons. " +
  "Fourteen functions, every one a visible row with its key printed on it. Two invisible guarantees: every sort lands in a versioned run " +
  "store that never overwrites an earlier result, and every run records exactly the parameters it used, so any result can be regenerated from its own record.");
title(s, "The workbench: the workflow on one screen");
const stages = [["d", "GET DATA", "files · probe · raw signal"],
                ["2", "SORT & CURATE", "sort · judge units · Phy"],
                ["3", "LOOK & SHARE", "report · GUI · compare"]];
stages.forEach(([k, name, what], i) => {
  const y = 2.0 + i * 1.5;
  card(s, 0.7, y, 4.6, 1.15);
  chip(s, 1.0, y + 0.31, k);
  s.addText(name, { x: 1.75, y: y + 0.12, w: 3.4, h: 0.5, fontFace: FONT, fontSize: 17,
    bold: true, color: ACCENT, margin: 0 });
  s.addText(what, { x: 1.75, y: y + 0.6, w: 3.4, h: 0.45, fontFace: FONT, fontSize: 12.5,
    color: SEC, margin: 0 });
});
card(s, 5.75, 1.7, 6.95, 5.0);
s.addImage({ path: img("tui_dashboard.png"), x: 5.95, y: 1.9, w: 6.55, h: 4.37 });

// ---- 5 · Intuition 1: SNR --------------------------------------------------
s = slide(
  "How does the workbench judge a unit? First intuition: size against the noise. After filtering and referencing, this recording's " +
  "noise floor is about 4 microvolts - and that number is a property of the recording, not the sorter: every one of the six sorters " +
  "we ran lands between 4.00 and 4.09. It is also our canary: if it ever reads about 1 microvolt, the amplitude scaling is wrong. " +
  "A real cell swings tens of microvolts - the demo run's average peak-to-peak is 34.4. The rule asks SNR of at least 4.");
title(s, "Judging a unit, intuition 1: bigger than the noise");
s.addImage({ path: img("fig_snr.png"), x: 1.5, y: 1.55, w: 10.3, h: 5.27 });

// ---- 6 · Intuition 2: ISI --------------------------------------------------
s = slide(
  "Second intuition: rhythm. After a spike, a neuron is silent for a millisecond and a half - the refractory period. One cell " +
  "leaves an empty window at the left of its interval histogram. When two cells wear one label, their spikes interleave and " +
  "that window fills in. The metric is the ISI violations ratio; at 1.0 the violations are as dense as a second neuron firing " +
  "at the unit's own rate. That is the workbench's tell for a merged unit, and you will see it flag our own data in a minute.");
title(s, "Intuition 2: a neuron cannot double-tap");
s.addImage({ path: img("fig_isi.png"), x: 1.35, y: 1.7, w: 10.6, h: 4.4 });
s.addText("shaded: the 1.5 ms refractory window", { x: 1.35, y: 6.2, w: 10.6, h: 0.4, align: "center",
  fontFace: FONT, fontSize: 12.5, italic: true, color: SEC, margin: 0 });

// ---- 7 · Honesty gates -----------------------------------------------------
s = slide(
  "Numbers only mean something if the tool refuses to flatter. Three standing rules. One: a unit that passes every criterion on " +
  "under 100 spikes is named a thin-evidence pass, never called strong - at that count the criteria are counting almost nothing. " +
  "Two: a metric that could not be computed stays 'not judged' - NaN never becomes a verdict, in either direction. Three: the " +
  "split advisory you are about to see changes no verdict and no count - it points, you decide. The quality rule itself is " +
  "SNR at least 4, ISI ratio at most 0.5, amplitude cutoff at most 0.1, presence at least 0.9, and it is tunable per lab.");
title(s, "Honest by construction");
const gates = [
  ["Thin evidence is named", "a pass on < 100 spikes is never called “strong”"],
  ["“Could not judge” stays said", "a missing metric is never a verdict"],
  ["Advice, not autopilot", "the split advisory changes no verdict - it points, you decide"],
];
gates.forEach(([head, body], i) => {
  const x = 0.7 + i * 4.2;
  card(s, x, 2.2, 3.8, 3.1);
  s.addText(head, { x: x + 0.3, y: 2.6, w: 3.2, h: 1.1, fontFace: FONT, fontSize: 19,
    bold: true, color: ACCENT, margin: 0 });
  s.addText(body, { x: x + 0.3, y: 3.8, w: 3.2, h: 1.2, fontFace: FONT, fontSize: 14,
    color: SEC, margin: 0 });
});

// ---- 8 · Demo --------------------------------------------------------------
s = slide(
  "Live demo, three keys. Press 2: sort the recording - tridesclous2, about half a minute on this laptop. Press u: the judgment " +
  "screen - every unit with its verdict, its evidence, and the advisory where it fires; label a unit good, unsure, or noise and " +
  "the decision is recorded with its reason. Press 3: the report - the same story as one shareable page. If the demo gods object, " +
  "the appendix has screenshots of every screen.");
title(s, "Live: sort it, judge it, share it", { y: 1.5, fontSize: 40, align: "center", w: 11.9 });
const demo = [["2", "sort"], ["u", "judge"], ["3", "report"]];
demo.forEach(([k, verb], i) => {
  const x = 2.6 + i * 3.0;
  s.addShape(pres.ShapeType.roundRect, { x, y: 3.3, w: 1.5, h: 1.5, rectRadius: 0.12,
    fill: { color: ACCENT }, line: { type: "none" }, shadow: shadow() });
  s.addText(k, { x, y: 3.3, w: 1.5, h: 1.5, align: "center", valign: "middle",
    fontFace: "Courier New", fontSize: 44, bold: true, color: WHITE, margin: 0 });
  s.addText(verb, { x: x - 0.25, y: 4.95, w: 2.0, h: 0.5, align: "center",
    fontFace: FONT, fontSize: 18, color: ACCENT_SOFT, margin: 0 });
  if (i < 2) s.addShape(pres.ShapeType.rightArrow, { x: x + 1.75, y: 3.85, w: 0.9, h: 0.4,
    fill: { color: PERI }, line: { type: "none" } });
});
s.addText("(backup screenshots in the appendix)", { x: 0.7, y: 6.3, w: 11.9, h: 0.4, align: "center",
  fontFace: FONT, fontSize: 12.5, italic: true, color: SEC, margin: 0 });

// ---- 9 · The verdict on our recording -------------------------------------
s = slide(
  "So what does it say about our own data? First: it finds the neurons. Against the hand-sorted reference - seven units on four " +
  "electrodes - the default sorter recovers 97 to 100 percent of every unit's spikes. The four cells we accepted in curation match " +
  "the hand sort at 97.5 to 100 percent. Then the honest catch: on the three electrodes that carry two hand-sorted neurons, " +
  "those pairs come back as ONE unit each - and the ISI flag fires on exactly those merged units, ratios 1.06 to 1.36 on thousands " +
  "of spikes, precisely the two-cells-one-label signature from the intuition slide. The tool caught its own sorter's mistake.");
title(s, "On our recording: found, and honestly flagged");
s.addText("97-100%", { x: 0.7, y: 1.7, w: 3.6, h: 1.1, fontFace: FONT, fontSize: 48, bold: true,
  color: ACCENT, margin: 0 });
s.addText("of every hand-sorted unit's spikes, recovered", { x: 0.7, y: 2.85, w: 3.4, h: 0.9,
  fontFace: FONT, fontSize: 15, color: SEC, margin: 0 });
card(s, 4.5, 1.65, 8.2, 2.3);
s.addImage({ path: img("fig_recovery_strip.png"), x: 4.7, y: 1.85, w: 7.8, h: 1.56 });
s.addText("recovery per hand-sorted unit (sweep page)", { x: 4.7, y: 3.45, w: 7.8, h: 0.35, align: "center",
  fontFace: FONT, fontSize: 11.5, italic: true, color: SEC, margin: 0 });
s.addShape(pres.ShapeType.roundRect, { x: 0.7, y: 4.45, w: 12.0, h: 1.9, rectRadius: 0.09,
  fill: { color: "F7EBD4" }, line: { type: "none" }, shadow: shadow() });
s.addText("the honest catch", { x: 1.1, y: 4.7, w: 11.2, h: 0.45, fontFace: FONT, fontSize: 15,
  bold: true, color: AMBER, margin: 0 });
s.addText("each electrode's PAIR comes back as one merged unit - and the ISI flag fires on exactly those units, as designed",
  { x: 1.1, y: 5.2, w: 11.2, h: 0.9, fontFace: FONT, fontSize: 17, color: INK, margin: 0 });

// ---- 10 · The shootout -----------------------------------------------------
s = slide(
  "Would a different algorithm split those pairs for free? We ran the whole recording through six sorters - three local, two more " +
  "in Docker - and judged every one against the hand sort with the same matcher: a split means two DISTINCT units, each carrying " +
  "one of the electrode's two neurons at 80 percent or better. Eighteen pair verdicts, zero splits. Where a sorter finds the " +
  "neurons at all, it hands back one unit carrying both; the others lose neurons outright - waveclus finds 3 units total. " +
  "And every sorter's noise floor reads 4.00 to 4.09 microvolts: same recording, same physics. So no free lunch from swapping algorithms - " +
  "which makes the untangling routes on the next slide the real path.");
title(s, "The shootout: no sorter splits the pairs");
card(s, 1.25, 1.55, 10.8, 5.55);
s.addImage({ path: img("fig_pair_matrix.png"), x: 1.45, y: 1.75, w: 10.4, h: 5.15 });

// ---- 11 · Untangling routes ------------------------------------------------
s = slide(
  "Three named routes out. One: Phy - press y and the hard cases export with everything Phy needs; split there, and the verdicts " +
  "import back into the same audited record. Two: the lab's Windows machine has an NVIDIA GPU, which unlocks Kilosort4 - a " +
  "template-matching generation that resolves overlapping cells far better; same workbench, same judgment, stronger sorter. " +
  "Three: this is not a one-recording trick - the advisory needs no reference, so on any new recording it points at the units " +
  "worth a second look using only their own spike counts, SNR, and intervals.");
title(s, "Untangling the pairs: three named routes");
const routes = [
  ["y", "Phy round trip", "export the hard cases, split by hand, verdicts return to the same record"],
  ["GPU", "Kilosort4 on the lab box", "the Windows + NVIDIA machine unlocks the stronger sorter generation"],
  ["✓", "Works on novel data", "the advisory needs no reference: new recordings get the same honest flag"],
];
routes.forEach(([k, head, body], i) => {
  const x = 0.7 + i * 4.2;
  card(s, x, 2.1, 3.8, 3.7);
  s.addShape(pres.ShapeType.roundRect, { x: x + 0.3, y: 2.45, w: 1.0, h: 0.62, rectRadius: 0.08,
    fill: { color: ACCENT }, line: { type: "none" } });
  s.addText(k, { x: x + 0.3, y: 2.45, w: 1.0, h: 0.62, align: "center", valign: "middle",
    fontFace: "Courier New", fontSize: 18, bold: true, color: WHITE, margin: 0 });
  s.addText(head, { x: x + 0.3, y: 3.3, w: 3.2, h: 0.8, fontFace: FONT, fontSize: 17.5,
    bold: true, color: ACCENT, margin: 0 });
  s.addText(body, { x: x + 0.3, y: 4.15, w: 3.2, h: 1.4, fontFace: FONT, fontSize: 13.5,
    color: SEC, margin: 0 });
});

// ---- 12 · Close ------------------------------------------------------------
s = slide(
  "What this buys the lab. Minutes instead of hours, on our own machines. Every claim auditable: each run records its exact " +
  "parameters and can be regenerated from its own record; results never overwrite each other. Honesty as a default: thin evidence " +
  "is named, unjudgeable stays unjudged, and the one real problem in our data was flagged by the tool itself, with named ways out. " +
  "All of it on SpikeInterface, the standard the field already shares. Questions - or if you want, the live screens again.");
title(s, "What this buys the lab", { y: 0.75, fontSize: 38 });
const buys = [
  ["Minutes", "not hours, per recording"],
  ["Auditable", "every run regenerable from its own record"],
  ["Never clobbered", "versioned runs, decisions with reasons"],
  ["Honest", "the tool flagged its own sorter's mistake"],
];
buys.forEach(([big, small], i) => {
  const x = 0.7 + (i % 2) * 6.2, y = 2.1 + Math.floor(i / 2) * 2.35;
  card(s, x, y, 5.7, 2.0);
  s.addText(big, { x: x + 0.35, y: y + 0.3, w: 5.0, h: 0.8, fontFace: FONT, fontSize: 27,
    bold: true, color: ACCENT, margin: 0 });
  s.addText(small, { x: x + 0.35, y: y + 1.15, w: 5.0, h: 0.6, fontFace: FONT, fontSize: 14,
    color: SEC, margin: 0 });
});
s.addText("built on SpikeInterface · the industry standard underneath", { x: 0.7, y: 6.85, w: 11.9,
  h: 0.4, align: "center", fontFace: FONT, fontSize: 13, italic: true, color: ACCENT_SOFT, margin: 0 });

// ---- Appendix: backup screenshots -----------------------------------------
function appendix(name, file, note, w, h) {
  const s2 = slide(note);
  s2.addText("Appendix · " + name, { x: 0.7, y: 0.35, w: 11.9, h: 0.55, fontFace: FONT,
    fontSize: 21, bold: true, color: ACCENT_SOFT, margin: 0 });
  const maxW = 11.9, maxH = 6.2, r = Math.min(maxW / w, maxH / h);
  const iw = w * r, ih = h * r;
  s2.addImage({ path: img(file), x: (13.33 - iw) / 2, y: 1.05 + (maxH - ih) / 2, w: iw, h: ih });
}
appendix("the dashboard", "tui_dashboard.png",
  "Backup: the dashboard. Three stages, fourteen visible functions, the RESULTS block with the takeaway, the thin-evidence line, and the amber split advisory.", 3000, 2000);
appendix("judging units", "tui_triage.png",
  "Backup: the judgment screen. Per-unit verdict with the rule's own words, the evidence card, and the split advisory on the merged units. Labels write an audited record.", 3000, 2000);
appendix("the report", "appendix_report.png",
  "Backup: report.html. The verdict block with run identity, the strong-units story, the recovery column against the hand sort, and the split-evidence section with per-unit ISI histograms.", 1200, 950);
appendix("the sorter shootout page", "appendix_sweep.png",
  "Backup: sweep.html. The full shootout: verdict up top, 18 pair verdicts, recovery per hand-sorted unit, noise-floor canary, and the exact parameters every run used.", 2400, 1900);

pres.writeFile({ fileName: OUT }).then(() => console.log("wrote " + OUT));
