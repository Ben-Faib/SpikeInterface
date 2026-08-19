# SEALS.md - what each run decided, moved, and needs from Ben

*Ben's read-in-30-seconds file, and the source `/status` reads. Every sealing session appends
ONE block here (five lines, one sentence each - the cap is the point), updates the pinned
lines below if its work changed them, and edits the OPEN block if it created or closed a
need. Long prose belongs in ROADMAP, LESSONS, the briefs, and commit messages - never here.
A need left only in a chat summary is a need Ben never sees.*

---

## Where we stand (pinned - any seal that changes one of these rewrites the line)

- **The pipeline works end to end on the one recording**: load → sort (4 local sorters,
  Docker fallback) → analyzer + six array/yield metrics on four surfaces → report/compare;
  noise-floor canary steady at ~4 µV across all saved sorts.
- **The curation loop is live** (W1 s2 `cddd677` + s3 `96a53cb`): merge/split/label
  decisions persist in an anchored record beside the sort, replay onto a curated Sorting
  with re-scored metrics, every surface states curated-vs-raw honestly, and the hard cases
  round-trip through Phy (`phy` menu action / `export-phy` → curate → `import-phy`, verdicts
  landing back in the same record with source="phy"); records and manifests refuse a sort
  they weren't written against (tdc2 non-determinism makes that refusal load-bearing).
  In-TUI triage (`f594a31`) labels the same record from the dashboard (u), and the
  W1 science arc is complete.
- **Runs are versioned and regenerable** (W2, `482d68d`): every sort lands in its own
  run dir with complete provenance; the current run is an atomically-replaced pointer
  a smoke run can never take; records/curated/phy ride inside their run; regeneration
  from a record prints an honest match report with measured tolerances (no unit-count
  criteria - tdc2 non-determinism is design law).
- **Probe geometry is real** (`nnx-a1x16-3mm-100` default); channel→site identity wiring
  is the accepted STANDING ASSUMPTION (Ben, 2026-08-19: no adapter map is coming; reopen
  only if one ever arrives).
- **Deployment target is the UPitt lab's Windows+GPU box**; Windows Docker-sort cleanup
  crash fixed 2026-08-18 (`7940f96`); GPU-sorter enablement (kilosort4) not yet started (WD).
- **The takeaway surface (face1) is on main** (`8f651f2`, 2026-08-19): every surface -
  report, dashboard RESULTS, triage - reads ONE rollup (sort_summary.unit_rollup) with
  tri-state honesty (strong / passes-on-thin-evidence / sub-threshold / not judged), the
  report leads with the run-stamped strong-units block and the manual-.nev RECOVERY
  column (both match directions, after a review caught the containment inversion hiding
  100% recoveries as "no match"), and docs/WORKFLOW.md is the plain-language guide.
- **The dashboard is the workflow** (face2, `dd90687`, 2026-08-19): a state block over
  ONE list of all fourteen functions in GET DATA · SORT & CURATE · LOOK & SHARE, every
  row a visible labeled key saying what it produces, rows never yielding (smaller
  terminals scroll, never clip); help teaches the real workflow in WORKFLOW.md's words;
  DESIGN_UX §2 is the redesign's spec of record.
- **The product demo exists on main's store** (the clean pass, 2026-08-19): fresh full
  sort → run `20260819-035117-c7184d` (16 units, canary 4.086 µV) → all 16 units
  labeled through the REAL TUI triage (4 good = the cells recovering Ben's manual units
  at 97.5–100%; 8 unsure; 4 noise - three evidence-keyed rules, every decision
  audit-trailed with source=tui) → applied (curated re-score, canary 4.03 µV) → report,
  dashboard and compare all reading that one run id, curated-stated.
- **The presentation arc is delivered** (CONDUCTOR v4, 2026-08-19): the em-dash purge is
  total and pinned (`tests/test_no_em_dashes.py`); the merge advisory answers "do I need
  to split?" on novel data from ONE home (sort_summary: >= 1000 spikes + solid SNR + ISI
  >= 2x the rule's ceiling, bimodality corroborating) and is quoted by report, triage and
  dashboard; the parameter round trip is verified with two real defects fixed; the
  five-sorter sweep is MEASURED LAW: 18 pair verdicts, ZERO splits (no swept sorter
  separates the merged pairs; canary 4.00-4.09 uV across all six), told honestly on
  `outputs/sweep.html`; the report leads its advisory with the evidence (per-unit ISI +
  amplitude histograms); every HTML surface reads the one validated periwinkle palette
  (`scripts/viz_palette.py`); and the ~10 min lab-meeting deck exists
  (`outputs/lab_meeting_deck.pptx`, regenerable via `docs/presentation/make_deck.js`:
  12 slides + 4-screenshot appendix, full speaker script with the real numbers in the
  notes, no credits).
- **The repo is unified**: one branch (main), pushed; every side branch deleted after
  merge verification; conductor v3 closed 2026-08-19; conductor v4 closed 2026-08-19.
  Facts of record binding design: E1's premise FALSE in-band (PRE1), tdc2 non-deterministic
  (14–19 units across identical runs), .nev unit ids are PER-ELECTRODE SLOTS (7 sorted
  electrode×slot units on 4 electrodes; CSV reconciled row-for-row), and the recording's
  accepted-unit picture is 4 strong cells (ch 5·7·9·11 electrodes) recovered at 96-100%
  (measured again on the face1 full run: 99.6% / 100% / 100% / 96.3%).
  Product facts on record: built by Benjamin Faibussowitsch with Aleece Al-Olimat for
  UPitt researchers on industry-standard SpikeInterface.

## OPEN - needs Ben

- **DECK - the dry read**: open `outputs/lab_meeting_deck.pptx` in PowerPoint and read
  the notes script aloud once (the file passes the validator and renders cleanly in
  LibreOffice, but a headless session cannot click through PowerPoint itself); two
  things to know while reading: the advisory fires on 6 units, the 4 known merges plus
  units 17 and 2 which genuinely meet the criteria, and `.si_menu.json` now pins
  `active_sorter: tridesclous2` so a bare `report` stays on the demo run despite the
  sweep's new sorts. *(opened 2026-08-19)*
- **WD - lab-box access**: the Windows+GPU deployment track starts with one session on
  that machine. *(opened 2026-08-18)*
- **W3 - the face pick**: the takeaway surface and the binned-rows dashboard are landed;
  the fuller direction, and the lab-requirements pass that shapes it (users, fluency,
  curation-vs-batch pain), is still his call. *(narrowed 2026-08-19)*
- **W4 - lab recordings**: multi-recording work starts when real lab data arrives.
  *(opened 2026-08-18)*

Resolved by Ben 2026-08-19 (the interview): the QUALITY-RULE item closed as a decision:
defaults stay; the path is split-the-merges (diagnosis advisory + Phy prep now, Ben
splits later) with a sorter sweep testing whether another algorithm splits without Phy.
P3 closed as a STANDING ASSUMPTION: no adapter map is coming; identity wiring is
accepted; reopen only if a map ever arrives. Both feed THE CONDUCTOR v4 / GOAL_PRESENT.

---

## The ledger (newest first)

**2026-08-19 - CONDUCTOR v4 CLOSED: the presentation arc, all eight items sealed, pushed**
- Did: closed the run: the sweep page (review: ship, seven findings folded including the
  split-verdict exclusivity guard and the honest partial-coverage headline), the report
  facelift + content audit (review: fix-first, all nine findings folded: the log-axis ISI
  label now lands on its line, captions derive from data, ghost panels hidden), the
  comparison pages on the palette with the pre-existing dead agreement heatmap fixed
  (category axes), and the deck built LAST from the finished pieces (16 slides with the
  full spoken script and real numbers in notes, validator clean, LibreOffice-rendered
  and eyeballed slide by slide).
- Means: Aleece can walk into Tracy's lab meeting with a deck whose every number traces
  to a surface a skeptic can open: found (97-100% recovery), honestly flagged (the ISI
  advisory on exactly the merged units, evidence drawn in the report), no free lunch
  (18 pair verdicts, zero splits), and named ways out (Phy round trip, Kilosort4 on the
  lab box).
- Moved: final gates all green on main: suite 723 + 2 documented skips, 11 snapshots,
  launch check OK, smoke canaries 3.966-4.054 uV this run, em-dash pin green, push set
  verified free of data and large blobs; CLAUDE.md gained viz_palette + sweep_page
  ownership rows and the no-em-dash convention; LESSONS S9 filed.
- Needs Ben: the DECK dry-read item in OPEN (batched there with its two need-to-knows);
  nothing else.
- Next: the deck is presented from `outputs/lab_meeting_deck.pptx`; the remaining board
  is WD (lab box) · W3 (fuller face) · W4 (lab recordings).

**2026-08-19 - CONDUCTOR v4 mid-run: purge sealed, advisory + params reviewed, sweep measured**
- Did: sealed GOAL_PRESENT items 1-4 - the em-dash purge (4 waves, ~3160
  occurrences, 7 snapshots deliberately re-baselined, repo-wide pin test
  `tests/test_no_em_dashes.py`, stray run deleted, P3 reworded as the standing
  assumption), the merge advisory (sort_summary owns it: >= 1000 spikes + solid
  SNR + ISI >= 2x the rule's ceiling, bimodality corroborates; report callout,
  triage card line, dashboard RESULTS chip - Fable review folded, its HIGH
  finding fixed by recording n_spikes/bimodality in summary.json at sort time
  with saved runs backfilled), parameter integrity (round trip verified; two
  real defects found and fixed: repr-vs-JSON argv encoding and the editor's
  None-default rendering; 18 tests; review: ship), and the five-sorter sweep
  through the store (all six full runs canary 4.00-4.09 uV).
- Means: the workbench now tells a researcher WHEN to split (on novel data, in
  plain words, from one home), parameter editing provably runs what it shows,
  and the shootout question is answered with measurements: ZERO splits in 18
  pair verdicts - no swept sorter separates the pairs tridesclous2 merges
  (spykingcircus2/lupin/simple/mountainsort5/waveclus all merge or miss), so
  the Phy and GPU routes carry the untangling story, exactly the deck's arc.
- Moved: suite 713 green at the fold; the periwinkle palette is built and
  machine-validated in both modes (scripts/viz_palette.py, the one home);
  the sweep page's Fable review and the report facelift build run now.
- Needs Ben: nothing yet - the batch lands at the run close.
- Next: fold the sweep review, land the facelift + its review, then the deck
  from finished pieces, board close, push.

**2026-08-19 - THE INTERVIEW: Ben's presentation-arc decisions taken on record, v4 filed**
- Did: ran the structured interview (three rounds) and encoded every decision into
  `goals/GOAL_PRESENT.md` (the complete spec: merge-diagnosis advisory, five-sorter
  sweep judged by pair-splitting, sweep-results page with parameters stated, report
  facelift + content audit, periwinkle palette validated across all surfaces, the
  ~10 min lab-meeting .pptx with speaker script in notes, the no-em-dash hard
  boundary) plus THE CONDUCTOR v4 prompt in ROADMAP.
- Means: the next session opens with zero ambiguity: audience, length, format, demo
  shape, framing (honest current state + escape routes), palette, and boundaries are
  all decisions of record, not guesses.
- Moved: the quality-rule OPEN item resolved (split path, defaults unchanged); P3
  re-scoped to a standing assumption; the stray run's deletion is queued in v4.
- Needs Ben: nothing until the v4 run seals; then a dry read of the deck script.
- Next: paste THE CONDUCTOR v4 from ROADMAP into a fresh session.

**2026-08-19 - CONDUCTOR v3 CLOSED: the clean pass, one branch, pushed**
- Did: ran the product demo end-to-end on main through the store - fresh full sort
  (run `20260819-035117-c7184d`, 16 units, canary 4.086 µV) → all 16 units labeled
  through the real TUI triage by three evidence-keyed rules (good = recovers a manual
  cell ≥90%: u4/u8/u10/u16 at 99.7/100/98.3/97.5% of ch5#2/ch9#2/ch11#1/ch7#1;
  unsure = under the 100-spike floor or 10–20% overlap with a real cell; noise = judged,
  gross ISI, no recovery) → apply → report + compare --nev - then unified the repo
  (all seven merged side branches deleted; the W2 lane -D'd after verifying every
  commit has a landed counterpart on main; worktrees removed and pruned) and pushed.
- Means: every surface now tells one coherent story against one run id - report:
  "tridesclous2 · curated · run 20260819-035117-c7184d · 2026-08-19 03:54 · 132 s
  window - no unit passes the rule on solid evidence · 5 pass it on thin evidence
  (ch 2·1·8·7·7)"; dashboard RESULTS: "tridesclous2 · 0 strong units of 16 · 132 s
  sorted · curated (16 decisions) / 5 units pass the rule only on thin evidence
  (ch 2·1·8·7·7)  u triage / V_pp 34.44 µV · SNR 5.38 · noise 4.03 µV · yield 81.2%
  (13/16)" - and the labels are Ben's real, editable curation record.
- Moved: the demo's first curated pass caught the run stamp printing the anchor dict
  where the run id belongs (fixed + pinned, `2e10ae3`); final gates on main - full
  suite green, real launch check OK, push set verified free of data/large blobs.
- Needs Ben: the quality-rule OPEN item (his four real cells fail ISI ≤ 0.5 at
  1.06–1.36 on this run - merge-inflated; edit labels anytime with u); the inert stray
  run dir noted in the face1 seal; everything else on the board is the four gated items.
- Next: the four gated OPEN items are the whole board - P3 (adapter map) · WD (lab
  box) · W3 (fuller face pick) · W4 (lab recordings).

**2026-08-19 - face2: every function a visible row in three workflow stages (`dd90687`)**
- Did: rebuilt the dashboard to Ben's three decisions - a state block (DATA/PROBE ·
  SORT · RESULTS) over one grouped list of all fourteen functions (GET DATA · SORT &
  CURATE · LOOK & SHARE), each row an inverse-video key chip + verb-noun title + a dim
  what-it-produces phrase; a new yield ladder whose rows never yield; HELP_TOPICS
  rewritten around which-question → which-surface → which-key in WORKFLOW.md's
  vocabulary; DESIGN_UX §2 rewritten as the spec of record - with the Fable review's
  ship verdict and findings 1–4 folded (PageUp/PageDown landing on a disabled heading
  deadened Enter; the f folder chip's mouse route; two doc truths), F5 recorded.
- Means: a researcher reads the screen cold and sees the whole workflow - triage, Phy
  export, params, probe and verify included, none hidden behind bare letter keys - and
  the help finally teaches the app that exists instead of June's three-step version.
- Moved: suite 659 green on main (all 16 no-data skips run here), 4 dashboard
  snapshots deliberately re-baselined and reviewed, real-controller launch check OK;
  1–6 keep their historical meanings (WORKFLOW.md and muscle memory beat monotonic
  chip order - reviewer concurred).
- Needs Ben: nothing new - open the dashboard; it's his three decisions live, and he
  amends the landed result.
- Next: the clean pass on main (the product demo), then unify + push + close.

**2026-08-19 - face1: the takeaway surface, two reviews folded, landed (`8f651f2`)**
- Did: landed the takeaway slice - sort_summary.unit_rollup as the one home for
  strong/thin/sub-threshold/not-judged verdicts with plain-words isolation phrases,
  the report leading with the run-stamped strong-units block + manual-.nev recovery
  column, the dashboard RESULTS takeaway, triage strong-first, docs/WORKFLOW.md -
  with TWO independent Fable reviews folded (this session's and the peer
  conductor's, coordinated live via a baton handoff after both sessions turned out
  to be working the same slice; LESSONS S8).
- Means: the workbench now CONCLUDES instead of just computing - and honestly: the
  reviews caught the match column inverting the best news (100% recoveries worded
  "no match above chance") and the headline flattering 30-spike units as "strong",
  both fixed at the one home so report, dashboard and triage cannot disagree.
- Moved: suite 646 green on main (625 + 21), canary 4.077 µV on the fresh full
  sort; the four manual neurons measured recovered at 96.3–100% on run
  20260819-022506-8daaea; match_manual now pins to the run the report shows.
- Needs Ben: the quality-rule threshold call now in OPEN (the default buries his
  four real cells on ISI while nothing passes on solid evidence); an inert stray
  run dir `outputs/tridesclous2/runs/20260819-022232-4e9932` (peer's accidental
  main-tree sort, pointer untouched) - delete or keep at leisure.
- Next: face2 (the binned-rows dashboard redesign) builds now in this session,
  then the clean pass, unify + push, close.

**2026-08-19 - CONDUCTOR v2 RUN CLOSED: the queue is done (`482d68d` + seals)**
- Did: landed all three parked lanes plus the gate they opened - W1 s2 (curation
  lifecycle), s3 (Phy round trip, recovered from an uncommitted worktree), s4 (in-TUI
  triage), and W2 (versioned run store + provenance + regenerate) - each with a Fable
  review folded, and closed with the full gate set on main: suite 624+1 loud-skip →
  625-equivalent, smoke canary 4.058 µV with the store's smoke-refusal proven live,
  real launch check OK (verify_launch's stale managebar selector fixed in passing).
- Means: the workbench now takes raw Blackrock files to curated, defensible single
  units - anchored records, TUI triage, Phy round trip, versioned never-clobbering
  runs, and regeneration with honest measured criteria - the product promise of the
  W1+W2 arc, on main.
- Moved: mid-run, Ben's .nev semantics questions were answered with measurements
  (per-electrode slots; the CSV reconciled row-for-row; chance-level cross-electrode
  coincidence) and his "where is the takeaway" directive became the face track's
  first slice (lane-face1, building now: per-contact strong-units view + workflow
  guide).
- Needs Ben: nothing for the close - relaunch the menu to get the store + triage,
  then one clean full sort → u triage → apply on a run that can never be clobbered.
- Next: face1 lands with its review; then the four gated items (P3/WD/W3/W4) are
  the whole remaining board.

**2026-08-19 - W2: the reproducibility engine, integrated last as planned (`482d68d`)**
- Did: landed the versioned run store (per-run dirs + atomic current pointer, smoke
  runs refused as current with the incumbent pinned, legacy layouts readable),
  complete provenance (effective params, seed, probe + geometry hash, preprocessing
  chain, versions, git sha, recording identity), regenerate-from-record with
  tolerances calibrated on seven measured run pairs (containment floor 0.85 against
  worst honest 0.903; params and recording identity now exact-compared), config-as-
  code export, and the curation re-point - records and curated results ride inside
  the run they describe.
- Means: a result the lab publishes is now regenerable from its own record with an
  honest match report, a quick smoke can never displace a full sort, and the exact
  22:21-vs-01:09 clobber that burned Ben tonight is impossible.
- Moved: the two Fable passes (lane + integration) folded eleven findings and the
  integration caught two latent bugs (bare report resolving a run id as a sorter on
  fresh clones; the online compare page never naming its run); tdc2 non-determinism
  observation extended (16 units at 01:09, 17 at 01:18); five follow-ups recorded in
  the brief.
- Needs Ben: nothing.
- Next: run close above.

**2026-08-19 - W1 s4: in-TUI unit triage, reviewed ship, landed (`f594a31`)**
- Did: landed the triage screen - unit list + NaN-honest per-unit evidence card off
  disk, g/m/n/u writing through curation.py's API (source="tui") behind a live
  anchor re-check via the new pure `anchor_error()`, reviewed n/N, stale/refused
  states verbatim with named next steps, a pressable "u triage" chip on RESULTS -
  with the Fable review's verdict ship, all four judgment calls accepted, and its
  four hardening minors recorded in the W1 brief.
- Means: a researcher can triage a sort without leaving the terminal, and every
  label lands in the same anchored record the CLI, report, and Phy round trip
  read - the W1 curation track is now feature-complete (rule → lifecycle → Phy →
  TUI).
- Moved: suite 534 green on main (11 snapshots; the three dashboard re-baselines
  verified text-identical except the chip); the reviewer replicated the write
  path live and the byte-unchanged-record refusal; W1's remaining work is
  follow-up hardening only.
- Needs Ben: nothing - press u on a sorted result when curious.
- Next: W2 integration lands last (in lane now), then the run close.

**2026-08-19 - W1 s3: the Phy round trip, recovered, reviewed fix-first, landed (`96a53cb`)**
- Did: recovered the lane's never-committed work from the temp worktree, rebased it onto
  s2's folded schema, ran its Fable review (fix-first), folded all three must-fixes -
  the `--out` rmtree guard (an explicit target could have deleted the raw sort wholesale),
  blank-anchor refusals on BOTH sides of the trip (the reviewer reproduced labels landing
  on the wrong sort through an anchorless manifest), and the stale-curated export refusal -
  and landed it: `phy` menu action, export with identity manifest + id map + seeded labels,
  import keyed by the map with source="phy" provenance and named refusals.
- Means: the measured dead-end (tdc2's merges unsplittable by any modest method - residue
  3.6–5.4×) now has its human path: the hard cases go out to Phy and the verdicts come back
  into the same record every surface reads, with wrong-sort/wrong-sorter/stale/anchorless
  folders refused by name rather than quietly mis-imported.
- Moved: suite 514 at the fold (516 on main with the peer's `ff518fd`); raw + curated
  exports exercised live and the shipped artifact regenerated post-fix; six review
  follow-ups (F4–F8, F10) recorded in the W1 brief; CLAUDE.md's actions line + brief
  updated.
- Needs Ben: nothing - F8 (Phy's exact label-snippet syntax) waits on any machine with Phy
  installed.
- Next: s4 (in-TUI triage) builds in its lane; W2's review findings fold in parallel;
  W2 integrates last, re-pointing curation's sort_paths through the run store.

**2026-08-18 - W1 s2: the curation lifecycle, landed and validated fresh (`cddd677`)**
- Did: rebased the review-folded lane onto main (one semantic conflict: PRE1's bad-channel
  note + s2's curation provenance now coexist in the report), ran the whole validation
  chain fresh on the main tree - full 19-unit anchor sort (canary 4.114 µV) → label+split
  record → apply → curated 20 units re-scored (canary 3.993 µV) → both compare pages
  against the manual .nev - and added curation.py's ownership row + commands line to
  CLAUDE.md.
- Means: a lab member can now save merge/split/label decisions against exactly the sort
  they made them on, replay them into a first-class curated result, and trust every
  surface to say which result it is showing - with the anchor refusing a re-sorted tree
  (the non-determinism evidence made that refusal the design's load-bearing wall).
- Moved: the fresh sort extended the tdc2 non-determinism record to 14/16/17/18/19 units;
  s3's unmade handoff commit was recovered from the scratchpad worktree and rebased onto
  the folded schema (LESSONS S5 vindicated); three follow-ups recorded in the W1 brief
  (run_sorting seam promotion, import-gui, seeded GMM split).
- Needs Ben: nothing.
- Next: s3's live export/import validation + Fable review, then the s4 gate.

**2026-08-18 - CONDUCTOR RUN closed mid-flight at Ben's request: 4 sealed, 3 parked**
- Did: sealed P2, PRE1, D6 and DEBT with per-slice Fable reviews folded, and parked
  W1 s2 (`c1af408`, all 9 review findings folded), W1 s3 (`lane-w1s3`) and W2
  (`467ed7e`, honest handoff) on branches with the re-entry queue filed as ROADMAP's
  THE CONDUCTOR v2 prompt.
- Means: main (`c580286`) is 459-green and four slices stronger, and the two facts
  that reshape the science are measured and sealed - no bad channel exists in the
  referenced band (E1's premise false; detection kept as insurance) and tridesclous2
  is non-deterministic here (14/16/18 units), which now binds curation anchoring and
  W2's regeneration criteria.
- Moved: the s2 review's adversarial pass CONFIRMED the merged ch5/ch9 pairs are
  unreachable as defensible units by any modest splitter (3.6-5.4× residue
  contamination; leverage is upstream) - the Phy/human path for hard cases is now
  evidence, not preference; W1 s4 pre-assigned to the peer, gated on s2.
- Needs Ben: nothing new - paste THE CONDUCTOR v2 from ROADMAP into a fresh session.
- Next: v2's queue - land s2 (rebase + fresh validation), s3, open the s4 gate, W2
  (review + first-run regenerate + tests), then final suite + real launch + close.

**2026-08-18 - DEBT: the five recorded debts, closed in one lane (`0127dac`)**
- Did: keyboard-sortable report headers (real buttons, aria-sort state), the D2b
  pending-phase manifest (`plan` event, SHAPES-gated, modal shows pending rows),
  online_unit_labels/unit_class relocated to blackrock_io as the one home, five
  provably-dead controller members deleted, and extra-.nev discovery made robust.
- Means: the extra-.nev item was a REAL latent bug - with the manual export beside the
  recording, discovery returned the first name-sorted `.nev` and was right by luck;
  it now prefers the stem carrying data and refuses honestly, naming candidates, when
  genuinely ambiguous (one sealed test deliberately flipped from pins-the-guess to
  pins-the-refusal).
- Moved: Fable review ship (five low findings, four folded - ambiguity reason now
  reaches the compare page and the Data Setup checklist; probes.py catalog helpers
  deleted as the next dead layer; sort hint surfaced on the report); combined-code
  validation after rebases: 459 green, smoke canary 3.919 µV; CLAUDE.md's two stale
  loader bullets refreshed in the seal commit.
- Needs Ben: nothing.
- Next: recorded cosmetic (report th-padding dead-click zone) rides the debt list;
  W1 s2 integration is the next merge.

**2026-08-18 - D6: the airy dashboard (peer session, `98f2645`)**
- Did: replaced the boxed-panel chrome with Ben's approved whitespace + hairline
  language - crest tall-terminals-only, probe stated once, a pressable t-chip "change"
  control on SORT (click opens the picker), a dim context sentence, inverse-video key
  chips on action rows, the manage/help keys merged into one bottom line, and air wired
  into the yield order to collapse before content - with DESIGN_UX §2 rewritten as the
  spec of record.
- Means: the dashboard reads as sections of air instead of boxes, every affordance looks
  pressable (Ben's "less annoying" intent), and 80×24 stays fully usable with never-clip
  and painted-rows still pinned.
- Moved: the Fable review went fix-first and caught the flagship hairline never actually
  painting (word-wrapped out of its 1-row clip - and my first snapshot re-baseline had
  enshrined the bug) plus a resize-under-modal never-clip violation; all seven findings
  folded, the hairline test now asserts the paint, and the snapshots were re-baselined a
  deliberate second time; suite 441 green, real-controller launch verified.
- Needs Ben: nothing - open the dashboard when convenient; it's his mock synthesis live.
- Next: the debt bundle merges onto this (conductor), and W1s4's triage screen inherits
  the D6 section language.

**2026-08-18 - PRE1: bad channels out of the reference - premise measured false, feature kept (`c823f55`)**
- Did: built data-driven bad-channel detection/exclusion into the sort pipeline
  (mad, pinned seed, 25% wholesale-refusal, manual naming, provenance on every
  surface), archived the baseline, re-ran the full sort + manual comparison to
  measure it, and folded all eight findings of a fix-first Fable review.
- Means: E1's premise is false in the referenced band - ch1's oscillation is
  sub-300 Hz and the bandpass removes it before the median (in-band ch1 is the
  quietest channel and carries a real unit; zero channels flagged by any method),
  so the sort is unchanged and the feature is insurance for the lab's recordings.
- Moved: tridesclous2 measured NON-DETERMINISTIC here (14/16/18 units across
  identical runs) - W1's curation records now hard-anchor to their exact sort and
  W2's regeneration criteria avoid unit counts; baseline + MEASUREMENT.md live in
  outputs/_archive/tridesclous2_pre_badch/.
- Needs Ben: nothing.
- Next: W2 launches off this commit; debt bundle (reviewed: ship) integrates
  behind it; W1 s2 under review, s3 building.

**2026-08-18 - P2: multi-shank / ProbeGroup support (peer session, `8af8111`)**
- Did: a multi-probe ProbeGroup (or a probe with native shank ids) now imports as one
  self-contained profile - shank labels and per-shank pitch/density materialised, group
  wiring validated as one permutation across all contacts and pinned channel→shank→
  position verbatim by test, build reconstructing shanks with an honest outline - with
  the Fable review's five actionable findings folded pre-seal.
- Means: the lab's multi-shank probes drop into the library like any other, density
  classing stays physical (global contact proximity, not shank labels - so sorter fits
  can't be fooled either way), and the report's probe view shows shanks as real columns
  with zero report changes.
- Moved: gates in an isolated worktree (main outputs/ left to PRE1): suite 388 green, 48
  probe unit tests, 30 s multi-shank sort at noise floor 3.993 µV, both shank columns in
  the analyzer and report; save_profile now also shields wiring/shank keys from
  stripping upserts.
- Needs Ben: nothing.
- Next: P3 (wiring surfaces) inherits three recorded items - the --probe-file identity
  trap (P1), coincident-probes error wording, and per-shank display consumption by the
  menu lane when its probe UI pass lands; conductor flips the P2 row.

**2026-08-18 - W1 slice 1: the quality rule, owned and honest (+ Option A adjudicated)**
- Did: replaced the hardcoded SNR≥5 headline with a configurable, NaN-honest,
  provenance-recorded quality rule owned by sort_summary and stated verbatim on every
  surface that shows the count, with its review's seven findings folded (including the
  result card claiming the old rule over new-rule numbers).
- Means: the "N look high-quality" signal is now defensible and tunable
  (.si_menu.json quality_rule), and "couldn't judge" can never masquerade as "failed".
- Moved: Ben chose the curation path; Option A self-resolved - spykingcircus2 smears
  units across channels on this data, so tridesclous2 + curation is confirmed; the
  manual .nev export is the validation reference for slice 2.
- Needs Ben: nothing - slice 2 (the curation loop: save merge/split/label decisions,
  apply, re-score) is next and is a full-session build.
- Next: W1 slice 2 in a fresh session from the board; the run's 17 seals stand.


**2026-08-18 - D5 + C2: the actions-first screen, and the manual sort answered (`63fe05c`, `4ffcfda`)**
- Did: rebuilt the main screen to Ben's late directive (actions primary, sorter list
  behind a filtering t-picker, RESULTS section, MANAGE line) with its review's two
  invisible-to-the-suite bugs fixed and pinned; and wired Ben's manually sorted .nev
  into the comparison machinery (--nev, --delta-ms, a containment column).
- Means: a first-time lab member lands on what they can do; and the sorter question is
  answered with numbers - tridesclous2 finds 97-100% of every manually sorted unit's
  spikes but merges each channel's pair into one unit, which is also exactly why its
  active-channel ISI violations run high (the huge ratios elsewhere are the metric's
  low-rate blowup, not brokenness).
- Moved: a measured ~0.6 ms crossing-vs-peak timestamp offset is now compensated and
  documented in the compare defaults; params were checked (all defaults - not the
  cause); repo memory corrected twice about the .nev.
- Needs Ben: nothing blocking - next-step options are his: a spykingcircus2 full-sort
  comparison, tdc2 clustering tuning, or W1 curation (splitting merges is exactly that
  slice, and the manual export is now its validation reference).
- Next: W1 curation is the highest-value queued science; T-track follow-ups and the
  D5-review's noted controller dead code ride the next pass.


**2026-08-18 - T2/T3: journeys + honesty states (peer session, `fc4652b` + `7e6938d`)**
- Did: retired six layout-detail assertions the redesign obsoleted (each enumerated in the
  commit message), added four journeys that cross the real screens and the real subprocess
  event pipe (explore→sort→report with chain and reopen, cancel-mid-sort with the child
  provably dead cross-platform, the failure card with its log→ next step, 0-unit amber
  reaching the dashboard), and pinned every §1.7 dead-end to NAME its next step.
- Means: the suite now defends what must stay true - flows and honesty - while visual
  change stays a deliberate snapshot re-baseline, so future redesign slices can't be
  fought by chrome assertions or pass while a dead-end goes nameless.
- Moved: the review surfaced the Windows Esc-mid-sort orphan (fixed in D4 `f115015`, now
  asserted universally); the five D4 flow-modal tests ride in `7e6938d` by agreed commit
  order, with D4-review F8a/F8b folded in; suite 382 green.
- Needs Ben: nothing new - the standing report-eyeball ask above covers it.
- Next: the T track is complete; future surfaces inherit the journey/state doctrine now
  written into tests/README.md.

**2026-08-18 - D3 + D4: the report and the flow modals (`d12ff5c`, `f115015`)**
- Did: sealed the overhaul's last two built slices - the verdict-first report (four honest
  stat tiles, truthful TOC glyphs, reader-order sections, one chart language; built by a
  builder agent, hardened by a fix-first review) and the flow modals (informed sort-span
  choice from real wall-time provenance, live param validation with ● marks, compare
  behind an honest BusyScreen with failure causes surfaced, bare gui/sort crashes fixed,
  and Esc-mid-sort now genuinely kills the worker tree on Windows).
- Means: every surface Ben screenshotted this afternoon is rebuilt to the approved spec
  and on main, verified by 382 tests, per-slice Fable reviews, and a real launch.
- Moved: D3b (report/compare progress plumbing) is unblocked and READY; C1 (Ben's
  NEV online-vs-sorted comparison) has its engine building in a lane now.
- Needs Ben: open outputs/report.html - the redesign's only unperformed check is a human
  eyeball in a real browser (no Chrome connection tonight from any session).
- Next: peer seals T2/T3 (in progress); then C1 review + menu wiring and D3b.


**2026-08-18 - B1: bare report crash fixed (peer session, `b43869e`)**
- Did: the documented bare invocations (`make_report.py`, the launcher's report action, and
  the silent non-TTY dispatch CI/piped runs hit) now resolve a sorter - explicit flag >
  persisted active sorter with a saved sort > the most-complete saved sort - instead of
  crashing on a None path join, and error honestly (naming a command that works) when
  nothing is saved.
- Means: the report front door works with zero arguments, and the default it picks is the
  most complete sort rather than a leftover 30 s smoke - the review talked us out of the
  queued recommended-default step on exactly that scenario.
- Moved: 9 regression tests pin the precedence and the exact reported command; isolated
  worktree suite 341 green; review verdict ship (7 findings, 4 folded in).
- Needs Ben: nothing.
- Next: siblings recorded, not fixed - bare `gui` and bare `sort` still crash on a None
  sorter (pre-existing; a good D4-adjacent small fix).

**2026-08-18 - D1: the dashboard overhaul (`18a5279`)**
- Did: rebuilt the dashboard to the approved spec - two-line banner, one home for the
  active sorter, six numbered workflow actions over a dim MANAGE tier, signal-budget
  sorter rows with honest availability glyphs, folded GPU group, compact scrollable
  INSPECTING, a persistent LAST RESULT line with r-reopen, persisted active sorter, and
  truthful help - with the layout driven by real budget arithmetic instead of hand-tuned
  thresholds.
- Means: the first surface of Ben's overhaul is live, and it stays usable at 80×24 - the
  Fable review caught the redesign starving the lists at exactly that size (fix-first, 7
  findings) and every finding is fixed with painted-rows tests pinning it.
- Moved: D4 and B1 unblocked (D1 released the menu files); the D2 view half can start
  (its engine half sealed the same evening as `fc19579` - the protocol now carries
  elapsed, per-phase durations, and a result payload, Fable-reviewed ship).
- Needs Ben: nothing - the run continues autonomously per the standing authorization.
- Next: D2 view half (progress modal + result cards), then D3 report, D4, B1.

**2026-08-18 - P1 probeinterface import (peer session)**
- Did: probes.py now imports probeinterface .json/.prb via CLI, materialising geometry
  (positions, pitch, layout, wiring, provenance) into a self-contained library profile
  with honest channel-count verdicts and named refusals (partial wiring, ProbeGroups,
  name collisions, unwritable store), hardened per the Fable review (`384884e`).
- Means: a probe the lab already has a standard description for drops straight in - real
  density-based sorter fits included - instead of being hand-entered parameter by
  parameter, and declared wiring is honoured rather than silently discarded.
- Moved: gates ran in an isolated worktree against HEAD (main tree churns with D1/D2):
  suite 313 green, 30 s sort with an imported probe at noise floor 3.984 µV, report probe
  section faithful, mismatch asymmetry intact; review verdict ship, 3 medium findings all
  folded in.
- Needs Ben: nothing new.
- Next: D1 should make imported probes view/duplicate/delete-only in the probe editor
  (a geometry-less rename now fails honestly instead of saving a broken probe), and P3
  inherits the on-record `--probe-file` identity-wiring trap plus tetrode-import classing.

**2026-08-18 - T1 testing harness (peer session)**
- Did: built the redesign safety net - 8 deterministic SVG snapshot baselines of today's
  dashboard + modals (pytest-textual-snapshot in the dev group), a fresh-build structural
  golden check for the report, contract tests locking the sort-progress protocol (shapes,
  ordering, emitter, stdout purity), and tests/README.md's re-baselining procedure
  (`6171816`) - plus the 10-finding DESIGN_UX feasibility critique (`a11b259`, folded in).
- Means: D-track sessions can rewrite every visible surface and land it as reviewable
  SVG/structure diffs, with the protocol's extension points pre-agreed (new event types
  gate on the SHAPES table; new optional keys flow free; done/error stay as-is).
- Moved: the suite is 302 tests / ~30 s, green including a fresh report build; the Fable
  review returned 7 findings, none blocking, all six actionable ones folded in pre-seal.
- Needs Ben: nothing new - the D0 veto stays the gate this work serves.
- Next: D1/D2 re-baseline snapshots deliberately per tests/README.md; ROADMAP's T1 node
  needs flipping to done (orchestrating session owns that file this run).

**2026-08-18 - M1: quality metrics widened**
- Did: widened per-unit quality metrics from 3 to 12 columns with dependency-aware,
  best-effort compute ordering, honest NaN rendering everywhere, and a Fable review whose
  four findings (NaN-sort, silent-skip visibility, stale README, degenerate-PCA caveat)
  are all folded in.
- Means: every downstream surface - the report today, D3's verdict tiles, W1's curation
  thresholds - now stands on a real evidence base instead of 3 metrics.
- Moved: D3 lost its M1 gate (only the D0 veto remains); B1 filed (pre-existing bare
  `report` crash, reproduced on unmodified code, prompt READY in ROADMAP).
- Needs Ben: nothing new - the D0 veto remains the big open item.
- Next: paste P1 or B1 from ROADMAP; veto DESIGN_UX.md when ready.

**2026-08-18 - overhaul kickoff (D0 + graph)**
- Did: took Ben's overhaul directive on record (NORTHSTAR: UPitt researchers, varied probes,
  Faibussowitsch × Al-Olimat), drafted the `DESIGN_UX.md` D0 spec from screenshots of every
  surface, wrote the GOAL_D/GOAL_T/GOAL_P briefs, dissolved W0 into the new dependency-graph
  queue, and dispatched T1 (testing harness) to the peer session.
- Means: the overhaul now has a design authority with a veto gate, a testing track that
  makes redesigns reviewable, and two engine prompts (M1 metrics, P1 probe import) that can
  run in parallel while the veto is pending.
- Moved: ROADMAP is a dependency graph; the false-green 0-unit fix, INSPECTING clip,
  active-sorter persistence, and help fixes now live inside D1/D2 with the spec behind them.
- Needs Ben: the D0 veto on DESIGN_UX.md (the big one), plus the standing arc/requirements/
  lab-box items.
- Next: Ben vetoes/amends the spec; meanwhile paste M1 and P1 from ROADMAP; T1 seals from
  the peer session.

**2026-08-18 - orchestrator install**
- Did: installed the decantv2-pattern build system - NORTHSTAR, LOOPS, six goal briefs,
  ROADMAP console, this file, LESSONS, four agents, verify-spike + status skills, CLAUDE.md
  wiring.
- Means: the workbench now has a stated product (Tracy's UPitt lab), a ratifiable arc, and
  sessions that seal against machine-checkable gates instead of drifting.
- Moved: W0's brief is verified-current against source (five of seven audit quick wins
  remain; Explore-figures and stderr-log already landed).
- Needs Ben: the three OPEN items above - arc ratification, the lab requirements pass, and
  lab-box access.
- Next: paste ROADMAP prompt 1 (W0 quick wins) in a fresh session.
