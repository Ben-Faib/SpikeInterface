# GOAL W4 — The Multi-Recording Lab Notebook: breadth, once depth is trustworthy

## Intent

The dataset's own name — `PFCM7_d0ephys_Block2` — declares a multi-session study, yet the
loader silently keeps the first file set in a folder and everything is one recording, one
sorter, one run. This phase (audit Path 2, WORKBENCH_DIRECTIONS.md §Path 2) adds the session
abstraction, batch processing, and cross-session views. It runs **last** by design: breadth
before W1/W2 scales un-publishable output.

## Gates

- W1 and W2 sealed.
- Real multi-session data from the lab on hand (more blocks/days of PFCM7 or successors) —
  building batch machinery against one file set is guesswork.
- **Cross-session unit tracking additionally waits on the verified adapter map** (NORTHSTAR
  open question): tracking units across days on an assumed channel wiring compounds a maybe
  into a method.

## Shape (to be sliced when the gates clear)

Recording discovery/selection (retiring the silent `candidates[0]` collapse in
`find_blackrock_base` with an explicit chooser), a headless batch driver over the W2 run
store, cross-recording comparison surfaces, and only then unit tracking.

## Boundaries

- The batch driver is a consumer of the W2 run store, never a second run store.
- Multi-recording UI lands in the chosen W3 face, not as a parallel surface.
- Loader extensions stay in `blackrock_io.py` (single source of truth) and keep the
  one-selector stream rule and NEV clock semantics.
