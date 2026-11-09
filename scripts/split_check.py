#!/usr/bin/env python3
"""The proof of a pure move (SPLIT.md, step 7): the checkout's pdfmd before and after the move must say and make the same.

    python3 scripts/split_check.py [--extra 'NAME:ARGS'] [--extra 'NAME!:ARGS'] ... [--real-data] [--keep]

"Before" is HEAD, checked out into a temporary git worktree; "after" is the working tree with the move not yet committed.
Both run the same fixed set, one after the other, in the same scratch folder (moved aside when its run is done, so every name
pdfmd derives from a path, such as the global cache folder's hash or the raw pictures map's, is the same in both), with an
empty config and a cache of their own:

- `--help` and every `--help TOPIC` (the topics are read from `--help`): byte for byte;
- `--verbose` builds: a document to PDF, `--to html`, `--to docx`, `-r` on examples/book, `-b -j 2`, and a document with
  comments of every kind (Markdown, LaTeX preamble, .bib, CSL) through `--assemble-only`, `--merge` and `--attach-source`:
  the logs line for line with the trees' own paths, times, dates, durations, time stamps in file names, temporary names and
  the mtimes and seconds of `--api` answers masked (a run with `-j` compares its lines sorted, as parallel workers print in
  any order), and the assembled, merged and attached text byte for byte;
- `--extra 'NAME:ARGS'` adds a build of the package's own feature, run in the scratch copy of examples/ (`{root}` in ARGS is
  the tree being run); NAME may not be a default build's. A build that fails in both trees proves nothing: it is reported
  (BOTH FAILED) and the result is not SAME, unless it is declared an intended failure, `--extra 'NAME!:ARGS'`, which must
  then fail in both (DID NOT FAIL otherwise);
- `scripts/pdfmd --version`, best and median of ten: told, not judged (a slower start is for the author to see).

The scratch copies hold the files git knows in examples/ (tracked, or untracked and not ignored) with their modification
times. The checkout gives HEAD's files its own time, so each file of the worktree whose content equals the working tree's
gets the working tree's modification time, and a choice by age (a tie between documents) goes the same way in both; the
files the move changed keep the checkout time. (The commit time for every file would make the documents tie in "before"
only, as "after" runs with their real times.)

XDG_DATA_HOME (pdfmd's installed tools: KaTeX, d2, Graphviz launchers) is a scratch folder both runs share, or with
`--real-data` the one the environment sets, for builds that need installed tools; the run says which. Builds read standard
input from /dev/null. Exit status 0 when everything is the same. `--keep` keeps the scratch folders and prints where they are.
"""

from __future__ import annotations

import argparse
import difflib
import filecmp
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


def git_files(tree: Path, *arguments: str) -> list[str]:
    listed = subprocess.run(["git", "-C", str(tree), "ls-files", "-z", *arguments], capture_output=True, check=True).stdout
    return [name for name in listed.decode("utf-8").split("\0") if name]


def same_times(head: Path) -> None:
    """The worktree's files whose content is the working tree's get its modification times (see the docstring)."""
    for name in git_files(head):
        old, new = head / name, ROOT / name
        if old.is_symlink() or new.is_symlink() or not old.is_file() or not new.is_file():
            continue
        if filecmp.cmp(old, new, shallow=False):
            stat = new.stat()
            os.utime(old, ns=(stat.st_atime_ns, stat.st_mtime_ns))


def scratch(tree: Path, out: Path) -> Path:
    """The documents, copied: a build writes beside its source, and neither tree may be touched."""
    work = out / "work"
    for name in git_files(tree, "--cached", "--others", "--exclude-standard", "--", "examples"):
        source, target = tree / name, work / name
        if source.is_file() and source.suffix != ".pdf":
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    fixture = work / "fixture"
    fixture.mkdir()
    (fixture / "comments.md").write_text(COMMENTS_MD, encoding="utf-8")
    (fixture / "preamble.tex").write_text(PREAMBLE, encoding="utf-8")
    (fixture / "refs.bib").write_text(BIB, encoding="utf-8")
    style = subprocess.run(["pandoc", "--print-default-data-file", "default.csl"], capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout
    (fixture / "style.csl").write_text(style.replace("<info>", "<!-- a CSL comment -->\n<info>", 1), encoding="utf-8")
    (work / "batch").mkdir()
    shutil.copy2(work / "examples" / "results.md", work / "batch" / "a.md")
    shutil.copy2(work / "examples" / "lecture.md", work / "batch" / "b.md")
    return work


def version(tree: Path) -> str:
    found = re.search(r'^PDFMD_VERSION = "([^"]+)"', (tree / "pdfmd.py").read_text(encoding="utf-8"), re.MULTILINE)
    return found.group(1) if found else "?"


def spellings(path: Path) -> list[str]:
    """Every way a log may spell ``path``: as given, resolved, and from `~` (pdfmd's display_path); the longest first."""
    found, home = {str(path), str(path.resolve())}, Path.home()
    found |= {"~/" + Path(form).relative_to(home).as_posix() for form in found
              if Path(form).is_relative_to(home) and Path(form) != home}
    return sorted(found, key=len, reverse=True)


def mask(text: str, tree: Path, out: Path) -> str:
    """Only what differs between two runs of the same code: places, times, random names, the version."""
    for path, name in [(out, "OUT"), (tree, "TREE"), (Path.home(), "~"), (Path(tempfile.gettempdir()), "TMP")]:
        for form in spellings(path):
            text = text.replace(form, name)
    text = text.replace(version(tree), "VERSION")
    text = re.sub(r"(?:/private)?/(?:var/folders|tmp)/\S*", "TMP", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2})?", "DATE", text)
    # time stamps in file names (snapshots 20261110091500, 20261110-091500 or 11-10_09-15-00; build records), with the
    # collision counter (-2) a second name in the same second gets
    text = re.sub(r"(?<!\d)(?:\d{8}-?\d{6}|\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:-\d{1,3})?(?!\d)", "STAMP", text)
    # durations: 12.3 s, and from a minute on 1:06, 1:01:06 or 2 d 01:01:06, one token for all (a build may cross 60 s)
    text = re.sub(r"\d+\.\d+ s\b", "N s", text)
    text = re.sub(r"(?<![\w:.])(?:\d+ d )?\d{1,2}(?::\d{2}){1,2}(?![\w:])", "N s", text)
    text = re.sub(r"\d+ ms\b", "N ms", text)
    text = re.sub(r'"(mtime|seconds)": ("?)[\d.]+\2', r'"\1": N', text)  # --api answers
    # tempfile's names: a prefix (`.b.pdfmd-title-`, `.results.pdfmd-`) and eight random characters; a bare `pdfmd-` only
    # after a dot, so that fixed names such as `pdfmd-manifest` stay
    return re.sub(r"((?<=\.)pdfmd-|pdfmd-[a-z]+(?:-[a-z]+)*-)[a-z0-9_]{8}(?![A-Za-z0-9_])", r"\1RANDOM", text)


def parallel(arguments: list[str]) -> bool:
    return any(re.fullmatch(r"-j\d*|--jobs(?:=.*)?", argument) for argument in arguments)


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


def run_tree(tree: Path, out: Path, extra: list[tuple[str, str]], data_home: Path | None) -> dict[str, object]:
    out.mkdir(parents=True)
    environment = {**os.environ, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(out / "config"),
                   "XDG_CACHE_HOME": str(out / "cache")}
    if data_home:
        environment["XDG_DATA_HOME"] = str(data_home)
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
    exits = {}
    for name, folder, arguments in runs:
        done = subprocess.run([*pdfmd, "--verbose", "--no-backup", *arguments], cwd=work / folder, capture_output=True,
                              stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", env=environment)
        log = mask(done.stdout + done.stderr, tree, out)
        if parallel(arguments):
            log = "".join(line + "\n" for line in sorted(log.splitlines()))
        result[f"log {name}"] = log + f"exit {done.returncode}\n"
        exits[name] = done.returncode
    result["exits"] = exits
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
                        help="one more --verbose build, run in the scratch copy of examples/; NAME!:ARGS for one that "
                             "must fail in both trees")
    parser.add_argument("--real-data", action="store_true",
                        help="use XDG_DATA_HOME as the environment sets it (installed tools), not a scratch one")
    parser.add_argument("--keep", action="store_true", help="keep the scratch folders")
    options = parser.parse_args()
    extra, failing = [], set()
    for item in options.extra:
        name, _, arguments = item.partition(":")
        if name.endswith("!"):
            name = name[:-1]
            failing.add(name)
        if not name or not arguments:
            parser.error(f"--extra {item!r}: NAME:ARGS or NAME!:ARGS")
        if name in {default for default, _, _ in RUNS} or name in {given for given, _ in extra}:
            parser.error(f"--extra {item!r}: {name} is the name of a default build or of an earlier --extra")
        extra.append((name, arguments))
    if not shutil.which("pandoc"):
        raise SystemExit("split_check needs Pandoc")
    base = Path(tempfile.mkdtemp(prefix="pdfmd-split-check-")).resolve()
    data = None if options.real_data else base / "data"
    if data:
        data.mkdir()
        print(f"data: a scratch XDG_DATA_HOME both runs share ({data})", flush=True)
    else:
        real = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        print(f"data: the environment's XDG_DATA_HOME ({real.replace(str(Path.home()), '~', 1)})", flush=True)
    before_tree, run = base / "head", base / "run"
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", "--quiet", str(before_tree), "HEAD"], check=True)
    try:
        same_times(before_tree)
        print("before: HEAD ...", flush=True)
        before = run_tree(before_tree, run, extra, data)
        run.rename(base / "before")
        print("after: the working tree ...", flush=True)
        after = run_tree(ROOT, run, extra, data)
        run.rename(base / "after")
    finally:
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(before_tree)], check=False)
    keys = sorted((set(before) | set(after)) - {"startup", "exits"})
    differ = set()
    for key in keys:
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        differ.add(key)
        print(f"DIFFERENT: {key}")
        if isinstance(old, str) and isinstance(new, str):
            sys.stdout.writelines(list(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "before", "after", n=1))[:40])
    for name in [name for name, _, _ in RUNS] + [name for name, _ in extra]:
        old, new = before["exits"][name], after["exits"][name]
        codes = f"exit {old}" if old == new else f"exit {old} before, {new} after"
        if name in failing and (old == 0 or new == 0):
            print(f"DID NOT FAIL: {name} ({codes})")
            differ.add(f"log {name}")
        elif name not in failing and old and new:
            print(f"BOTH FAILED: {name} ({codes})")
            differ.add(f"log {name}")
    (b_best, b_median), (a_best, a_median) = before["startup"], after["startup"]
    print(f"startup (scripts/pdfmd --version): before {b_best:.0f} / {b_median:.0f} ms, after {a_best:.0f} / {a_median:.0f} ms "
          "(best / median of ten)")
    print(f"NOT THE SAME: {len(differ)} of {len(keys)} checks differ" if differ else
          f"SAME: {len(keys)} checks (help, logs, outputs)")
    if options.keep:
        print(f"kept: {base}")
    else:
        shutil.rmtree(base, ignore_errors=True)
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
