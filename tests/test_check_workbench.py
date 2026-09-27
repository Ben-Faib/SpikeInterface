"""The confidence harness's sandbox rules (no sort is run here).

check_workbench.py promises it never touches real state: it runs from a throwaway
copy of the code whose REPO_ROOT is the copy, reading the recording in place.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import check_workbench as cw

ROOT = Path(__file__).resolve().parent.parent


def test_sandbox_holds_a_copy_of_the_code_and_points_at_the_data(tmp_path):
    box = cw.build_sandbox(ROOT, ROOT, parent=tmp_path)
    for src in (ROOT / "scripts").glob("*.py"):
        assert (box / "scripts" / src.name).read_bytes() == src.read_bytes()
    assert (box / cw.LAUNCHER).read_bytes() == (ROOT / cw.LAUNCHER).read_bytes()
    assert (box / cw.SANDBOX_MARKER).is_file()
    assert list((box / "outputs").iterdir()) == []
    cfg = json.loads((box / ".si_menu.json").read_text(encoding="utf-8"))
    assert cfg == {"data_dir": str(ROOT.resolve())}
    assert not any(p.suffix in (".ns5", ".ns2", ".nev") for p in box.rglob("*"))


def test_sandbox_repo_root_is_the_sandbox(tmp_path):
    box = cw.build_sandbox(ROOT, ROOT, parent=tmp_path)
    out = subprocess.run([sys.executable, "-c", "import blackrock_io as b; print(b.REPO_ROOT)"],
                         cwd=box / "scripts", capture_output=True, text=True, check=True)
    assert Path(out.stdout.strip()).resolve() == box.resolve()


def test_building_and_removing_the_sandbox_leaves_real_state_untouched(tmp_path):
    before = cw.snapshot_state(ROOT)
    box = cw.build_sandbox(ROOT, ROOT, parent=tmp_path)
    assert cw.remove_sandbox(box) and not box.exists()
    assert cw.state_changes(before, cw.snapshot_state(ROOT)) == []
