#!/usr/bin/env python3
"""Conductor health check: how heavy a repo's always-loaded and state files are, and where the weight is.

Usage: health.py [repo] [--json]. Read-only. Measures, per file: size (estimated tokens = chars/4), the share
of its text that is finished work (done items, struck rows, "done/live <date>" lines), dated lines older than
30 days, overlong lines, backticked repo paths that no longer exist, and sentences repeated across files.
Grades each file ok / heavy / bloated against the thresholds below; the grade is a prompt for a conversation
with Ben, never a licence to delete.
"""
import json, os, re, subprocess, sys
from datetime import date, datetime
from pathlib import Path

STATE = ["CLAUDE.md", "ROADMAP.md", "STATUS.md", "DECISIONS.md", "NORTHSTAR.md", "LOOPS.md", "LESSONS.md",
         "SEALS.md", "PRODUCT.md", "PLAN.md", "TODO.md", "NOTES.md", "AGENTS.md"]
# (heavy, bloated) estimated tokens; always-loaded files are held tighter because they cost every turn
LIMITS = {"always": (2500, 5000), "state": (8000, 20000)}
DONE = re.compile(r"(- \[x\]|~~.+~~|\*\*(done|live|closed|merged)\b|\b(done|live|closed|merged) 20\d\d-\d\d-\d\d)", re.I)
DATE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
PATH = re.compile(r"`([A-Za-z0-9_.\-]+/[A-Za-z0-9_./\-]+\.[a-z]{1,5})`")
SENT = re.compile(r"[^.!?\n]{90,}[.!?]")


def tokens(text): return len(text) // 4


def memory_index(repo: Path) -> Path:
    slug = str(repo.resolve()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug / "memory" / "MEMORY.md"


def always_loaded(repo: Path) -> list[Path]:
    out, d = [Path.home() / ".claude" / "CLAUDE.md"], repo.resolve()
    chain = []
    while True:
        chain.append(d / "CLAUDE.md")
        if d == Path.home() or d.parent == d: break
        d = d.parent
    out += [p for p in reversed(chain) if p.is_file() and p not in out]
    m = memory_index(repo)
    return [p for p in out + [m] if p.is_file()]


def tracked(repo: Path) -> list[str]:
    r = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.split("\n")
    out, skip = [], {"node_modules", ".git", ".venv", "venv", "__pycache__", ".next", "dist", "build"}
    for d, dirs, names in os.walk(repo):    # not a git repo (e.g. a folder of sub-repos): walk it
        dirs[:] = [x for x in dirs if x not in skip]
        out += [os.path.relpath(os.path.join(d, n), repo) for n in names]
        if len(out) > 300000: break
    return out


def exists(m: str, p: Path, repo: Path, files: list[str]) -> bool:
    """A cited path is alive if it resolves from the citing file or the repo, or any tracked file ends with it."""
    return (p.parent / m).exists() or (repo / m).exists() or any(f == m or f.endswith("/" + m) for f in files)


def measure(p: Path, repo: Path, kind: str, today: date, files: list[str]) -> dict:
    text = p.read_text(errors="replace")
    lines = text.splitlines()
    done = sum(len(l) for l in lines if DONE.search(l))
    old = 0
    for l in lines:
        ds = DATE.findall(l)
        if ds and all((today - datetime.strptime(x, "%Y-%m-%d").date()).days > 30 for x in ds if x[5:7] <= "12"):
            old += 1
    dead = sorted({m for m in PATH.findall(text) if not m.startswith(("out/", "http")) and not exists(m, p, repo, files)})
    t = tokens(text); heavy, bloated = LIMITS[kind]
    return {"file": str(p).replace(str(Path.home()), "~"), "kind": kind, "tokens": t, "lines": len(lines),
            "done_share": round(done / max(1, len(text)), 2), "old_dated_lines": old,
            "long_lines": sum(len(l) > 600 for l in lines), "longest_line": max((len(l) for l in lines), default=0),
            "dead_paths": dead[:8], "dead_count": len(dead),
            "grade": "bloated" if t > bloated else "heavy" if t > heavy else "ok"}


def repeats(files: list[Path]) -> list[dict]:
    seen = {}
    for p in files:
        for s in SENT.findall(p.read_text(errors="replace")):
            seen.setdefault(s.strip().lower(), set()).add(p.name)
    return [{"sentence": s[:120], "files": sorted(f)} for s, f in seen.items() if len(f) > 1][:10]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    repo = Path(args[0] if args else ".").resolve()
    today = date.today()
    always = always_loaded(repo)
    state = [repo / n for n in STATE if (repo / n).is_file() and (repo / n) not in always]
    files = tracked(repo)
    rows = [measure(p, repo, "always", today, files) for p in always] + [measure(p, repo, "state", today, files) for p in state]
    try:
        branches = subprocess.run(["git", "-C", str(repo), "branch", "--format=%(refname:short) %(committerdate:short)"],
                                  capture_output=True, text=True).stdout.split("\n")
        stale = [b for b in branches if b and (today - datetime.strptime(b.split()[-1], "%Y-%m-%d").date()).days > 21]
    except Exception:
        stale = []
    notes = Path.home() / ".claude" / "conductor" / f"{repo.name}.md"
    report = {"repo": str(repo), "always_loaded_tokens": sum(r["tokens"] for r in rows if r["kind"] == "always"),
              "files": rows, "repeated_sentences": repeats(always + state), "stale_branches": stale[:15],
              "conductor_notes": str(notes).replace(str(Path.home()), "~") if notes.is_file() else None}
    if "--json" in sys.argv:
        print(json.dumps(report, indent=1)); return
    print(f"# Health - {repo.name}\n\nAlways loaded every turn: ~{report['always_loaded_tokens']:,} tokens "
          f"(heavy over {LIMITS['always'][0]:,} a file).\n")
    print("| File | Kind | ~Tokens | Grade | Finished work | Dated >30 days | Lines >600 chars | Dead paths |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['file']} | {r['kind']} | {r['tokens']:,} | {r['grade']} | {int(100*r['done_share'])}% | "
              f"{r['old_dated_lines']} | {r['long_lines']} | {r['dead_count']} |")
    if report["repeated_sentences"]:
        print("\nSaid in more than one file:")
        for d in report["repeated_sentences"]: print(f"- {', '.join(d['files'])}: \"{d['sentence']}…\"")
    for r in rows:
        if r["dead_paths"]: print(f"\nDead paths in {r['file']}: {', '.join(r['dead_paths'])}")
    if stale: print(f"\nBranches untouched for 3+ weeks ({len(stale)}): {', '.join(b.split()[0] for b in stale[:10])}")
    print(f"\nConductor notes: {report['conductor_notes'] or 'none (run setup)'}")


if __name__ == "__main__":
    main()
