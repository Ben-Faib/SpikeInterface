"""Smoke test: confirm SpikeInterface is installed and can read this dataset.

Run it after creating the environment:

    conda activate si_env
    python scripts/verify_install.py

It prints library versions and a summary of the LFP recording (.ns2), the raw
broadband recording (.ns5/.ns6, if present), the installed sorters, the spike
units (.nev), and any digital event channels — without plotting anything, so it
works on a headless machine. If every section prints without an error, your
install is good.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make blackrock_io importable no matter what directory you launch this from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import blackrock_io as bio  # noqa: E402


def main() -> int:
    bio.use_utf8_stdout()  # so the final "✓" line can't crash on a Windows console
    print("=== Library versions ===")
    import spikeinterface as si

    print(f"spikeinterface {si.__version__}")
    import neo

    print(f"neo            {neo.__version__}")
    import probeinterface

    print(f"probeinterface {probeinterface.__version__}")

    base = bio.find_blackrock_base()
    print(f"\nData file set: {base.name}.*  (in {base.parent})")

    print("\n=== Analog (nsX) streams ===")
    for name, sid in bio.list_streams():
        print(f"  id={sid!r}  name={name!r}")

    print("\n=== LFP recording (.ns2) ===")
    rec = bio.read_lfp()
    print(f"  channels        : {rec.get_num_channels()}")
    print(f"  sampling rate   : {rec.get_sampling_frequency()} Hz")
    print(f"  duration        : {rec.get_total_duration():.2f} s")
    print(f"  first channels  : {list(rec.get_channel_ids()[:8])}")

    print("\n=== Broadband recording (.ns5/.ns6 — spike-sortable) ===")
    try:
        bb = bio.read_broadband(attach_probe=False)
        print(f"  channels        : {bb.get_num_channels()}")
        print(f"  sampling rate   : {bb.get_sampling_frequency()} Hz")
        print(f"  duration        : {bb.get_total_duration():.2f} s")
        print("  -> raw broadband present; you can run scripts/run_sorting.py")
    except Exception as err:
        print(f"  (no broadband stream: {err})")
        print("  -> only LFP present; add a .ns5/.ns6 to enable spike sorting")

    print("\n=== Installed sorters ===")
    import spikeinterface.sorters as ss

    print(f"  {ss.installed_sorters()}")

    print("\n=== Spike units (.nev) ===")
    sorting = bio.read_spikes()
    unit_ids = list(sorting.get_unit_ids())
    print(f"  sampling rate   : {sorting.get_sampling_frequency()} Hz")
    print(f"  number of units : {len(unit_ids)}")
    print(f"  unit ids        : {unit_ids[:20]}{' ...' if len(unit_ids) > 20 else ''}")
    total_spikes = sum(len(sorting.get_unit_spike_train(u)) for u in unit_ids)
    print(f"  total spikes    : {total_spikes}")

    print("\n=== Digital/serial events (.nev) ===")
    try:
        events = bio.read_events()
        if not events:
            print("  (no event channels)")
        for ev in events:
            print(f"  {ev['name']!r}: {len(ev['times'])} events")
    except Exception as err:  # event parsing is best-effort
        print(f"  (could not read events: {err})")

    print("\nAll good — SpikeInterface can read your data. ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
