"""`pdfmd --doc`: the documents of this version, offline: the list, one document, a part of one, and the search over their
headings and lines.

Moved out of `pdfmd.py` unchanged (v3.33.9, SPLIT.md), with `DOCUMENTS` and `DOC_URL`. `core` is the `pdfmd` module, bound when
the module is first loaded (the first binding wins); the pdfmd names the code uses (`PDFMD_VERSION`, `fence_after`, and
`cache_root` and `which`, which tests patch) are read as `core.X` when it runs. `document_file` finds the checkout's copy of a
document beside `core.__file__` (`pdfmd.py`); the bundled copy is found beside the package (`pdfmd_docs.__file__`) as before.
`webbrowser` is imported inside `doc_command`, as it was.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

core = None

DOCUMENTS = {
    "readme": ("README.md", "README.md", "the manual: every feature, with examples"),
    "recipes": ("recipes.md", "docs/recipes.md", "short worked examples"),
    "agents": ("agents.md", "docs/agents.md", "a short guide for a program or an AI assistant that runs pdfmd"),
    "changelog": ("CHANGELOG.md", "CHANGELOG.md", "what changed in every version"),
}


DOC_URL = "https://github.com/aliperdehan/pdfmd/blob/v{version}/{path}"


def document_file(name: str) -> Path | None:
    """The file of the document `name` (readme, recipes, agents, changelog): the bundled copy, else the checkout's own."""
    packaged, checkout, _ = DOCUMENTS[name]
    try:
        import pdfmd_docs
        found = Path(pdfmd_docs.__file__).resolve().parent / packaged
        if found.is_file():
            return found
    except ImportError:
        pass
    found = Path(core.__file__).resolve().parent / checkout
    return found if found.is_file() else None


def document_headings(text: str) -> list[tuple[int, int, str]]:
    """(line index, level, title) of each Markdown heading outside fenced code and HTML comments, in order."""
    found: list[tuple[int, int, str]] = []
    fence = ""
    in_comment = False
    for index, line in enumerate(text.splitlines()):
        if not fence:                                    # a comment hides its lines, headings included (a fence in one does not count)
            if in_comment:
                end = line.find("-->")
                if end < 0:
                    continue
                in_comment, line = False, line[end + 3:]
            line = re.sub(r"<!--.*?-->", "", line)
            start = line.find("<!--")
            if start >= 0:
                in_comment, line = True, line[:start]
        before, fence = fence, core.fence_after(fence, line)
        if before or fence:                              # a fence line, or a line of the code inside one
            continue
        if not fence:
            heading = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
            if heading:
                found.append((index, len(heading.group(1)), heading.group(2)))
    return found


def document_section(text: str, selector: str) -> tuple[str, str] | None:
    """(heading, text) of the part of a document `selector` names: a number counts the `##` headings (1 is the first), else a
    word the title has (the first heading that does, without regard to case); the part runs to the next heading of the same or
    a higher level. None when there is none."""
    headings = document_headings(text)
    lines = text.splitlines()
    chosen = None
    if selector.isdigit():
        second = [item for item in headings if item[1] == 2]
        if 1 <= int(selector) <= len(second):
            chosen = second[int(selector) - 1]
    else:
        wanted = selector.casefold()
        chosen = next((item for item in headings if wanted in item[2].casefold()), None)
    if chosen is None:
        return None
    start, level, title = chosen
    end = next((index for index, item_level, _ in headings if index > start and item_level <= level), len(lines))
    return title, "\n".join(lines[start:end]).rstrip() + "\n"


def search_documents(words: list[str], limit: int = 40) -> list[str]:
    """`name: Heading > Subheading (line N): the line` for each line of a document that has every word."""
    wanted = [word.casefold() for word in words]
    hits: list[str] = []
    for name in DOCUMENTS:
        path = document_file(name)
        if path is None:
            continue
        text = path.read_text(encoding="utf-8")
        headings = document_headings(text)
        trail: dict[int, str] = {}
        position = 0
        in_contents = False                              # the README's list of its own sections is not a place to find anything
        for index, line in enumerate(text.splitlines()):
            while position < len(headings) and headings[position][0] <= index:
                _, level, title = headings[position]
                trail = {key: value for key, value in trail.items() if key < level}
                trail[level] = title
                position += 1
            if line.strip() == "<!-- contents -->":
                in_contents = True
            if in_contents:
                in_contents = line.strip() != "<!-- /contents -->"
                continue
            if all(word in line.casefold() for word in wanted) and line.strip():
                where = " > ".join(trail[key] for key in sorted(trail)) or "(top)"
                hits.append(f"{name}: {where} (line {index + 1}): {line.strip()[:110]}")
                if len(hits) >= limit:
                    return hits
    return hits


def render_document(path: Path, title: str) -> Path | None:
    """The document as a web page in pdfmd's cache (made once per version and file; by Pandoc), or None without Pandoc."""
    if not core.which("pandoc"):
        return None
    target = core.cache_root() / "docs" / core.PDFMD_VERSION / (path.stem + ".html")
    if target.is_file() and target.stat().st_mtime >= path.stat().st_mtime:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    style = target.with_suffix(".css")
    style.write_text("body { font-family: system-ui, sans-serif; line-height: 1.5; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; }\n"
                     "pre, code { font-family: ui-monospace, monospace; font-size: .9em; } pre { overflow-x: auto; background: #f4f4f4; "
                     "padding: .6rem; } table { border-collapse: collapse; } td, th { border: 1px solid #ccc; padding: .2rem .5rem; }\n",
                     encoding="utf-8")
    command = ["pandoc", str(path), "-f", "gfm", "-s", "--toc", "--toc-depth=2", "--metadata", f"title={title}", "--css",
               style.name, "-o", str(target)]
    done = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", cwd=target.parent)
    return target if done.returncode == 0 and target.is_file() else None


def doc_command(words: list[str], print_only: bool, path_only: bool) -> int:
    """`pdfmd --doc [NAME [SECTION]]`, `--doc search WORD ...`."""
    if not sys.stdout.isatty() and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")        # the documents are UTF-8; a Windows pipe is the ANSI code page otherwise
        except (OSError, ValueError):
            pass
    if not words:
        print(f"Documents of pdfmd {core.PDFMD_VERSION} (pdfmd --doc NAME; --print for the Markdown, --path for the file):")
        for name, (_, _, what) in DOCUMENTS.items():
            path = document_file(name)
            size = f"{path.stat().st_size // 1024} KB" if path else "not bundled"
            print(f"  {name:<10}{size:>12}  {what}")
        print("  search WORD  the headings and lines that have the word (several words: all of them)")
        return 0
    first = words[0].casefold()
    if first == "search":
        if len(words) < 2:
            print("pdfmd --doc search takes a word: pdfmd --doc search stamp", file=sys.stderr)
            return 2
        hits = search_documents(words[1:])
        for hit in hits:
            print(hit)
        if not hits:
            print(f"Nothing in the documents has {' '.join(words[1:])!r}.")
        return 0 if hits else 1
    if first not in DOCUMENTS:
        print(f"pdfmd --doc: no document called {words[0]!r} (one of: {', '.join(DOCUMENTS)}, or search WORD)", file=sys.stderr)
        return 2
    path = document_file(first)
    if path is None:
        url = DOC_URL.format(version=core.PDFMD_VERSION, path=DOCUMENTS[first][1])
        print(f"{first} is not bundled with this copy of pdfmd (a checkout without it, or a zipapp). It is online: {url}",
              file=sys.stderr)
        return 1
    if path_only:
        print(path)
        return 0
    text = path.read_text(encoding="utf-8")
    if len(words) > 1:
        found = document_section(text, " ".join(words[1:]))
        if found is None:
            print(f"pdfmd --doc {first}: no section {' '.join(words[1:])!r} (a number counts the ## headings; "
                  "else a word of the title)", file=sys.stderr)
            return 1
        sys.stdout.write(found[1])
        return 0
    if print_only or not (sys.stdout.isatty() and sys.stdin.isatty()) or os.environ.get("PDFMD_NO_PROMPT"):
        sys.stdout.write(text)
        return 0
    page = render_document(path, f"pdfmd {core.PDFMD_VERSION}: {first}")
    if page is None:
        print("NOTE  no Pandoc to make a web page with: showing the Markdown", file=sys.stderr)
        sys.stdout.write(text)
        return 0
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print(f"{page}\n{page.as_uri()}")
        return 0
    import webbrowser
    if not webbrowser.open(page.as_uri()):
        print(f"{page}\n{page.as_uri()}")
    return 0
