#!/usr/bin/env python3
"""Writes fixtures/fixtures.js: what the web UI prototype shows instead of a server.

Everything here is made from the demo project in ../demo and from the real programs (`colophon export --list --json`,
`colophon settings list --json`, pandoc), never from anyone's own documents. The history and the checks are written by hand
(marked "sample") until pdfmd can say them in JSON (S1). Run: python3 tools/make_fixtures.py
"""
import json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DEMO = HERE / "demo"
HOME = str(Path.home())


def run(*cmd, stdin=None):
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=DEMO)
    if r.returncode:
        sys.exit(f"{cmd[0]} failed: {r.stderr.strip()[:300]}")
    return r.stdout.replace(HOME, "~")


files = {}
for p in sorted(DEMO.iterdir()):
    if p.is_file():
        files[p.name] = {"text": p.read_text(), "size": p.stat().st_size, "mtime": "2026-11-04T10:00:00Z"}

tree = [{"name": n, "kind": {"md": "markdown", "bib": "bib", "yaml": "metadata"}.get(n.rsplit(".", 1)[-1], "text")} for n in files]
# a main file of its own pick, with the reason (pdfmd's ranking will say this; here a sample)
project = {
    "name": "demo", "root": "demo", "main": "report.md",
    "mainWhy": "has a title, a bibliography and the most text",
    "discovered": [{"role": "metadata", "file": "metadata.yaml"}, {"role": "bibliography", "file": "refs.bib"}],
    "tree": tree,
}

# the outline: headings of every Markdown file, with their lines
outline = {}
for name, f in files.items():
    if not name.endswith(".md"):
        continue
    fence = False
    items = []
    for i, line in enumerate(f["text"].splitlines(), 1):
        if line.startswith("```"):
            fence = not fence
        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m and not fence:
            items.append({"level": len(m.group(1)), "title": m.group(2).strip(), "line": i})
    outline[name] = items

# the live HTML preview: CommonMark with source positions, so a block knows its line (data-pos="report.md@12:1-14:3")
preview = {}
for name in files:
    if name.endswith(".md"):
        html = run("pandoc", "-f", "commonmark_x+sourcepos+tex_math_dollars", "-t", "html", "--mathml", "--wrap=none",
                   "--citeproc", "--bibliography=refs.bib", "--metadata=link-citations:true", name)
        # sourcepos wraps every word in a span of its own: keep the position of the blocks, drop the word wrappers
        preview[name] = re.sub(r'<span data-wrapper="1" data-pos="[^"]*">(.*?)</span>', r"\1", html, flags=re.S)

exports = json.loads(run("colophon", "export", "--list", "--json"))
schema = []
for s in json.loads(run("colophon", "settings", "list", "--json")):
    for k in ("value", "changed"):
        s.pop(k, None)
    schema.append(s)

history = {
    "note": "sample: git log of the folder and pdfmd's build record, two lanes (the real ones come from pdfmd, S1)",
    "isRepo": True,
    "edits": [
        {"id": "a41c9d2", "when": "2026-11-04T09:41:00Z", "who": "A. Student", "title": "Results table and the slope", "files": ["report.md"], "plus": 14, "minus": 2},
        {"id": "7be0f13", "when": "2026-11-03T17:05:00Z", "who": "A. Student", "title": "Method: reagents and procedure", "files": ["report.md"], "plus": 22, "minus": 0},
        {"id": "03d77aa", "when": "2026-11-03T16:20:00Z", "who": "A. Student", "title": "Notes on the quench time", "files": ["notes.md"], "plus": 9, "minus": 0},
        {"id": "e19b5c0", "when": "2026-11-02T12:00:00Z", "who": "A. Student", "title": "First draft, bibliography", "files": ["report.md", "refs.bib", "metadata.yaml"], "plus": 31, "minus": 0},
    ],
    "builds": [
        {"id": "b-0042", "when": "2026-11-04T09:42:10Z", "title": "PDF, typst", "ok": True, "seconds": 1.4, "file": "report.md"},
        {"id": "b-0041", "when": "2026-11-04T09:30:02Z", "title": "PDF, lualatex", "ok": True, "seconds": 9.8, "file": "report.md"},
        {"id": "b-0040", "when": "2026-11-03T17:06:44Z", "title": "PDF, lualatex", "ok": False, "seconds": 3.1, "file": "report.md", "why": "Undefined control sequence, line 31"},
    ],
    "diff": {
        "a41c9d2": "@@ -27,9 +27,21 @@\n # Results\n \n-| t / min | V(NaOH) / mL |\n-|--------:|-------------:|\n+| t / min | V(NaOH) / mL | ln(V∞ − Vt) |\n+|--------:|-------------:|------------:|\n+| 0       | 12.1         | 2.75        |\n+| 10      | 14.3         | 2.51        |\n+| 20      | 16.0         | 2.27        |\n+| 30      | 17.4         | 2.01        |\n \n-The slope is not fitted yet.\n+The slope of the fitted line is $-0.0247\\ \\mathrm{min^{-1}}$.\n",
    },
}
checks = {"note": "sample: `pdfmd --check` as JSON (S1)", "items": [
    {"level": "warn", "file": "report.md", "line": 14, "message": "a reference to [@laidler1987] resolves, but the key is not in the metadata's `nocite`"},
    {"level": "info", "file": "report.md", "line": 33, "message": "the table has no caption; add `Table: ...` below it"},
]}
build = {"note": "sample build log", "lines": [
    "$ pdfmd report.md -t pdf -e typst", "pandoc 3.13 · typst 0.15.1", "reading metadata.yaml, refs.bib", "citeproc: 1 citation, 1 reference",
    "typst compile ... ok", "OK  report.md > report.pdf  (1.4 s)"]}

out = {"project": project, "files": files, "outline": outline, "preview": preview, "exports": exports, "settingsSchema": schema,
       "history": history, "checks": checks, "build": build}
out["syntaxes"] = json.loads((HERE / "syntax" / "syntaxes.json").read_text())      # the table the editor colours by; a page opened from disk cannot fetch it
text = "// generated by tools/make_fixtures.py: do not edit\nwindow.FIXTURES = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n"
(HERE / "fixtures" / "fixtures.js").write_text(text)
print("fixtures/fixtures.js", len(text), "bytes;", len(exports), "export rows;", len(schema), "settings;", sum(len(v) for v in outline.values()), "headings")
