#!/usr/bin/env python3
"""The proof of a pure move (SPLIT.md, step 7): the checkout's pdfmd before and after the move must say and make the same.

    python3 scripts/split_check.py [--extra 'NAME:ARGS'] ... [--keep]

"Before" is HEAD, checked out into a temporary git worktree; "after" is the working tree with the move not yet committed.
Both run the same fixed set in a scratch folder of their own, with an empty config and a cache of their own:

- `--help` and every `--help TOPIC` (the topics are read from `--help`): byte for byte;
- `--verbose` builds: a document to PDF, `--to html`, `--to docx`, `-r` on examples/book, `-b -j 2`, and a document with
  comments of every kind (Markdown, LaTeX preamble, .bib, CSL) through `--assemble-only`, `--merge` and `--attach-source`:
  the logs line for line with times, dates, temporary names and the build-record folder masked, and the assembled,
  merged and attached text byte for byte;
- `--extra 'NAME:ARGS'` adds a build of the package's own feature, run in the scratch copy of examples/ (`{root}` in ARGS is
  the tree being run);
- `scripts/pdfmd --version`, best and median of ten: told, not judged (a slower start is for the author to see).

Exit status 0 when everything is the same. `--keep` keeps the scratch folders and prints where they are.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COMMENTS_MD = """---
title: Comments
bibliography: refs.bib
csl: style.csl
pdfmd-options:
  strip-comments: true
---

<!-- a note to self, alone on its line -->

Text with <!-- inline --> a comment, and `<!-- in a code span -->` kept.

```
<!-- in a fence -->
```

    <!-- indented code -->

- item <!-- in a list -->

<!-- pdfmd: keep me -->

<!--
a comment over
two lines
-->

As shown [@doe].
"""
PREAMBLE = "% a preamble comment\n\\usepackage{xcolor} % trailing comment\n\\newcommand{\\x}{%\n  y}\n% !TEX program = lualatex\n"
BIB = "% outside the entries\n@book{doe, author = {Doe, Jane}, title = {A Book}, year = {2020}, publisher = {P}}\n"

RUNS = [  # name, folder of the scratch copy, arguments
    ("pdf", "examples", ["results.md", "-o", "results-out.pdf"]),
    ("html", "examples", ["results.md", "--to", "html", "-o", "results-out.html"]),
    ("docx", "examples", ["results.md", "--to", "docx", "-o", "results-out.docx"]),
    ("report", "examples", ["-r", "book", "-o", "book-out.pdf"]),
    ("batch", "batch", ["-b", ".", "-j", "2"]),
    ("assemble", "fixture", ["comments.md", "--assemble-only", "-o", "comments.assembled.md"]),
    ("merge", "fixture", ["comments.md", "--merge", "-o", "comments.merged.md"]),
    ("attach", "fixture", ["comments.md", "--attach-source", "--attach-csl", "-o", "comments.pdf"]),
]
OUTPUTS = ["fixture/comments.assembled.md", "fixture/comments.merged.md"]


def scratch(tree: Path, out: Path) -> Path:
    """The documents, copied: a build writes beside its source, and neither tree may be touched."""
    work = out / "work"
    shutil.copytree(tree / "examples", work / "examples", ignore=shutil.ignore_patterns("*.pdf"))
    fixture = work / "fixture"
    fixture.mkdir()
    (fixture / "comments.md").write_text(COMMENTS_MD, encoding="utf-8")
    (fixture / "preamble.tex").write_text(PREAMBLE, encoding="utf-8")
    (fixture / "refs.bib").write_text(BIB, encoding="utf-8")
    style = subprocess.run(["pandoc", "--print-default-data-file", "default.csl"], capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout
    (fixture / "style.csl").write_text(style.replace("<info>", "<!-- a CSL comment -->\n<info>", 1), encoding="utf-8")
    (work / "batch").mkdir()
    shutil.copy(tree / "examples" / "results.md", work / "batch" / "a.md")
    shutil.copy(tree / "examples" / "lecture.md", work / "batch" / "b.md")
    return work


def version(tree: Path) -> str:
    found = re.search(r'^PDFMD_VERSION = "([^"]+)"', (tree / "pdfmd.py").read_text(encoding="utf-8"), re.MULTILINE)
    return found.group(1) if found else "?"


def mask(text: str, tree: Path, out: Path) -> str:
    """Only what differs between two runs of the same code: places, times, random names, the version."""
    places = [(out, "OUT"), (tree, "TREE"), (Path.home(), "~"), (Path(tempfile.gettempdir()), "TMP")]
    for path, name in places:
        for form in sorted({str(path), str(path.resolve())}, key=len, reverse=True):
            text = text.replace(form, name)
    text = text.replace(version(tree), "VERSION")
    text = re.sub(r"(?:/private)?/(?:var/folders|tmp)/\S*", "TMP", text)
    text = re.sub(r"\d+\.\d+ s\b", "N s", text)
    text = re.sub(r"\d+ ms\b", "N ms", text)
    text = re.sub(r"builds/[^/\s]*-[0-9a-f]{8}/\d{8}-\d{6}(?:-\d+)?-(\w+)\.log", r"builds/RECORD-\1.log", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2})?", "DATE", text)
    # tempfile's names: a prefix such as `.b.pdfmd-title-` and eight random characters
    return re.sub(r"(pdfmd-[a-z]+(?:-[a-z]+)*-)[a-z0-9_]{8}(?![A-Za-z0-9_])", r"\1RANDOM", text)


def attachments(pdf: Path, tree: Path) -> dict[str, bytes]:
    try:
        import pypdf
    except ImportError:
        return {}
    if not pdf.is_file():
        return {}
    found = {}
    for name, contents in pypdf.PdfReader(str(pdf)).attachments.items():
        for index, data in enumerate(contents):
            if name.endswith("manifest.json"):
                data = re.sub(rb'\s*"created": "[^"]*",?', b"", data).replace(version(tree).encode(), b"VERSION")
            found[f"{index}-{name}"] = data
    return found


def run_tree(tree: Path, out: Path, extra: list[tuple[str, str]]) -> dict[str, object]:
    out.mkdir(parents=True)
    environment = {**os.environ, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(out / "config"),
                   "XDG_CACHE_HOME": str(out / "cache")}
    pdfmd = [sys.executable, str(tree / "pdfmd.py")]
    result: dict[str, object] = {}
    main_help = subprocess.run([*pdfmd, "--help"], capture_output=True, env=environment).stdout
    result["help main"] = main_help
    topics = re.search(rb"the options of one subject:\s*([a-z, ]+)", main_help)
    for topic in (topics.group(1).decode().replace(" ", "").split(",") if topics else []):
        done = subprocess.run([*pdfmd, "--help", topic], capture_output=True, env=environment)
        result[f"help {topic}"] = done.stdout + done.stderr
    work = scratch(tree, out)
    runs = RUNS + [(name, "examples", shlex.split(arguments.replace("{root}", str(tree)))) for name, arguments in extra]
    for name, folder, arguments in runs:
        done = subprocess.run([*pdfmd, "--verbose", "--no-backup", *arguments], cwd=work / folder, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=environment)
        result[f"log {name}"] = mask(done.stdout + done.stderr, tree, out) + f"exit {done.returncode}\n"
    for name in OUTPUTS:
        path = work / name
        result[f"file {name}"] = path.read_bytes() if path.is_file() else b"(missing)"
    for name, data in attachments(work / "fixture" / "comments.pdf", tree).items():
        result[f"attached {name}"] = data
    times = []
    for _ in range(12):
        start = time.perf_counter()
        subprocess.run([sys.executable, str(tree / "scripts" / "pdfmd"), "--version"], capture_output=True, env=environment)
        times.append((time.perf_counter() - start) * 1000)
    times = sorted(times[2:])
    result["startup"] = (times[0], statistics.median(times))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--extra", action="append", default=[], metavar="NAME:ARGS",
                        help="one more --verbose build, run in the scratch copy of examples/")
    parser.add_argument("--keep", action="store_true", help="keep the scratch folders")
    options = parser.parse_args()
    extra = []
    for item in options.extra:
        name, _, arguments = item.partition(":")
        if not name or not arguments:
            parser.error(f"--extra {item!r}: NAME:ARGS")
        extra.append((name, arguments))
    if not shutil.which("pandoc"):
        raise SystemExit("split_check needs Pandoc")
    base = Path(tempfile.mkdtemp(prefix="pdfmd-split-check-")).resolve()
    before_tree = base / "head"
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", "--quiet", str(before_tree), "HEAD"], check=True)
    try:
        print("before: HEAD ...", flush=True)
        before = run_tree(before_tree, base / "before", extra)
        print("after: the working tree ...", flush=True)
        after = run_tree(ROOT, base / "after", extra)
    finally:
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(before_tree)], check=False)
    same = True
    for key in sorted(set(before) | set(after)):
        if key == "startup":
            continue
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        same = False
        print(f"DIFFERENT: {key}")
        if isinstance(old, str) and isinstance(new, str):
            sys.stdout.writelines(list(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "before", "after", n=1))[:40])
    (b_best, b_median), (a_best, a_median) = before["startup"], after["startup"]
    print(f"startup (scripts/pdfmd --version): before {b_best:.0f} / {b_median:.0f} ms, after {a_best:.0f} / {a_median:.0f} ms "
          "(best / median of ten)")
    checked = sum(1 for key in before if key != "startup")
    print(f"SAME: {checked} checks (help, logs, outputs)" if same else "NOT THE SAME (see above)")
    if options.keep:
        print(f"kept: {base}")
    else:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
