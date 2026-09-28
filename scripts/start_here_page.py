#!/usr/bin/env python
"""Build START_HERE_WINDOWS.html from START_HERE_WINDOWS.md (the one source).

    uv run python scripts/start_here_page.py

The page is the Windows audit handoff with copy buttons: the markdown's prompt
(its ```text block) and its tools table are poured into the page template below,
so the two files can never disagree. Edit the markdown, then run this.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "START_HERE_WINDOWS.md"
OUT = ROOT / "START_HERE_WINDOWS.html"

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spike 2.0 Windows audit</title>
<style>
:root {
  --bg: #f6f7fb; --card: #ffffff; --ink: #151722; --muted: #5b6272; --line: #e2e5ee;
  --accent: #5d64ca; --accent-ink: #ffffff; --code-bg: #14141c; --code-ink: #e6e6f0;
  --ok: #1f8a4c; --warn: #9a6400;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #101016; --card: #17171f; --ink: #e6e6f0; --muted: #a3a2b3; --line: #2c2b38;
    --accent: #9b8cff; --accent-ink: #15141f; --code-bg: #0b0b10; --code-ink: #e6e6f0;
    --ok: #3fb950; --warn: #e3a008;
  }
}
:root[data-theme="dark"] {
  --bg: #101016; --card: #17171f; --ink: #e6e6f0; --muted: #a3a2b3; --line: #2c2b38;
  --accent: #9b8cff; --accent-ink: #15141f; --code-bg: #0b0b10; --code-ink: #e6e6f0;
  --ok: #3fb950; --warn: #e3a008;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
main { max-width: 920px; margin: 0 auto; padding: 40px 16px 64px; }
.eyebrow { color: var(--accent); font-weight: 700; letter-spacing: .06em; font-size: 13px;
  text-transform: uppercase; }
h1 { font-size: 34px; line-height: 1.2; margin: 6px 0 12px; }
h2 { font-size: 21px; margin: 40px 0 12px; }
p.lead { color: var(--muted); font-size: 17px; margin: 0 0 8px; }
.status { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 13px;
  border: 1px solid var(--line); color: var(--warn); margin: 8px 0 0; }
ol.steps { list-style: none; padding: 0; margin: 0; counter-reset: s; }
ol.steps > li { counter-increment: s; background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; padding: 18px 20px 18px 64px; margin: 0 0 14px; position: relative; }
ol.steps > li::before { content: counter(s); position: absolute; left: 20px; top: 18px;
  width: 30px; height: 30px; border-radius: 50%; background: var(--accent); color: var(--accent-ink);
  display: grid; place-items: center; font-weight: 700; }
ol.steps h3 { margin: 2px 0 6px; font-size: 17px; }
ol.steps p { margin: 6px 0; color: var(--muted); }
.code { position: relative; margin: 10px 0; }
.code pre { margin: 0; background: var(--code-bg); color: var(--code-ink); border-radius: 10px;
  padding: 14px 84px 14px 16px; overflow-x: auto; white-space: pre-wrap; word-break: break-word;
  font: 14px/1.55 ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace; }
.prompt pre { max-height: 560px; overflow-y: auto; }
button.copy { position: absolute; top: 10px; right: 10px; min-height: 36px; min-width: 64px;
  border: 1px solid #3a3946; background: #26243a; color: #e6e6f0; border-radius: 8px;
  font: 600 13px system-ui, sans-serif; cursor: pointer; }
button.copy:hover { background: #34314f; }
button.copy:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button.copy.done { background: var(--ok); border-color: var(--ok); color: #fff; }
code { font-family: ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace; font-size: .92em; }
table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; overflow: hidden; }
td { padding: 10px 14px; border-top: 1px solid var(--line); vertical-align: top; }
tr:first-child td { border-top: 0; }
td:first-child { white-space: nowrap; }
.note { color: var(--muted); font-size: 14px; }
@media (max-width: 560px) {
  h1 { font-size: 27px; }
  ol.steps > li { padding: 16px 16px 16px 56px; }
  ol.steps > li::before { left: 14px; }
  td:first-child { white-space: normal; }
}
</style>
</head>
<body>
<main>
  <div class="eyebrow">Spike 2.0 · branch Version-2</div>
  <h1>Start here: the Windows audit</h1>
  <p class="lead">Spike 2.0 has passed every automatic check on a Mac. Nothing has run on Windows yet.
  This page hands the whole Windows audit, functional and visual, to a Claude Code session on the lab machine.</p>
  <span class="status">Awaiting its Windows audit</span>

  <h2>Three steps</h2>
  <ol class="steps">
    <li>
      <h3>Get the branch</h3>
      <p>In PowerShell, in the folder where the project should live:</p>
      <div class="code"><pre>git clone -b Version-2 https://github.com/Ben-Faib/SpikeInterface.git
cd SpikeInterface</pre><button class="copy" aria-label="Copy clone commands">Copy</button></div>
      <p>Already cloned? Update it instead:</p>
      <div class="code"><pre>git fetch origin
git switch Version-2</pre><button class="copy" aria-label="Copy update commands">Copy</button></div>
    </li>
    <li>
      <h3>Put the recording in that folder</h3>
      <p>Next to <code>pyproject.toml</code>: <code>PFCM7_d0ephys_Block2.ns5</code>, <code>.ns2</code> and
      <code>.nev</code>. They are not in git; the <code>.ns5</code> is about 176 MB.</p>
    </li>
    <li>
      <h3>Open Claude Code in that folder and paste the prompt below</h3>
      <p>Leave it running. It takes about an hour and ends with a report in <code>docs\audits\</code>.</p>
    </li>
  </ol>

  <h2>The prompt</h2>
  <div class="code prompt"><pre id="prompt">@@PROMPT@@</pre><button class="copy" aria-label="Copy the prompt">Copy</button></div>
  <p class="note">The same prompt is in <code>START_HERE_WINDOWS.md</code>; this page is built from that file.</p>

  <h2>What the session will use</h2>
  <table>@@TABLE@@</table>
</main>
<script>
document.querySelectorAll("button.copy").forEach(function (btn) {
  btn.addEventListener("click", function () {
    var text = btn.parentElement.querySelector("pre").innerText;
    function done() {
      btn.textContent = "Copied";
      btn.classList.add("done");
      setTimeout(function () { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1600);
    }
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text; ta.setAttribute("readonly", "");
      ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); done(); } catch (e) {}
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else { fallback(); }
  });
});
</script>
</body>
</html>
"""


def main() -> int:
    md = MD.read_text(encoding="utf-8")
    prompt = re.search(r"```text\n(.*?)\n```", md, re.S).group(1)
    rows = re.findall(r"^\| `([^`]+)` \| (.+?) \|$", md, re.M)
    table = "".join(f"<tr><td><code>{html.escape(f)}</code></td><td>{html.escape(d)}</td></tr>"
                    for f, d in rows)
    page = TEMPLATE.replace("@@PROMPT@@", html.escape(prompt)).replace("@@TABLE@@", table)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.name}: {len(rows)} tools, prompt {len(prompt)} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
