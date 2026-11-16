"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_tex.plots`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from functools import lru_cache
from pathlib import Path

from pdfmd_base import core


PLOT_CACHE_FORMAT = "2"


PLOT_REQUEST_SEP = "@@|@@"


# The protocol between pdfmd and a LaTeX package that caches its pictures (v3.28.34; nothing in pdfmd names a package).
# A package opts in by mentioning `pdfmdCacheDir` in its style file. Then:
#   * pdfmd writes `\def\pdfmdCacheDir{<folder>/}\def\pdfmdCacheVersion{3}` before the document; the package looks a picture up
#     by its own key as `<folder>/<key>.pdf` with its size in `<folder>/<key>.dim`, and on a miss typesets inline and
#     appends `<key>@@|@@<macro>@@|@@<arguments>@@|@@<context>` as a line to `<job>.pdfmdreq`;
#   * after the build pdfmd runs each request in a standalone job with the same preamble, `\pdfmdCacheRender` defined (no
#     lookup then): the context, then `\setbox0\hbox{<macro><arguments>}`, the page is that box; its size goes to the .dim
#     file as `\gdef\pdfmdCacheWd`, `Ht` and `Dp` (a macro name each, in points);
#   * the context may carry two markers: PLOT_CTX_PLAIN splits it into a part read under expl3's catcodes and a part read with
#     the ordinary ones (settings with spaces in their names); PLOT_CTX_TWICE asks for two runs (a picture whose arrows
#     point at its own nodes: TikZ's remember picture needs the second run).
# A package that began before the protocol had neutral names says its own in `<package>-pdfmd.yaml` beside its style file
# (`picture-cache:` with `dir`, `render`, `requests` (a file suffix) and `wd`, `ht`, `dp`: macro names): they are defined
# and read as well (v3.28.37; until then the first package's names were a table here), and the helper counts as the
# handshake too.
CACHE_HANDSHAKE = "pdfmdCacheDir"


CACHE_ALIAS_KEYS = ("dir", "render", "requests", "wd", "ht", "dp")


PLOT_CACHE_KEEP_DIRS = 8     # per document: the whole report, a few parts, a package changed and changed back


PACKAGE_LOAD_RE = re.compile(r"\\(?:usepackage|RequirePackage|documentclass)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")


def picture_cache_styles(preamble: str) -> list[tuple[str, str, dict[str, str]]]:
    """(name, text, aliases) of the style files the preamble loads that take part in the picture cache protocol (they
    mention CACHE_HANDSHAKE, or their package helper has a `picture-cache:` mapping, the aliases), found by reading the
    packages it names: no package is named here."""
    found: list[tuple[str, str, dict[str, str]]] = []
    for names in PACKAGE_LOAD_RE.findall(re.sub(r"(?m)(?<!\\)%.*$", "", preamble)):
        for name in (item.strip() for item in names.split(",")):
            if not name or name in {item[0] for item in found}:
                continue
            path = core.kpsewhich_path(name if name.endswith((".sty", ".cls")) else name + ".sty")
            text = core.read_text_or_none(path)
            if text is None:
                continue
            helper = core.package_helper(path.resolve().parent, path.stem)      # as office_packages: through a symlink
            wanted = helper[0].get("picture-cache") if helper else None
            aliases = {key: str(value) for key, value in wanted.items()
                       if key in CACHE_ALIAS_KEYS and re.fullmatch(r"\.?[A-Za-z@.]+", str(value))} \
                if isinstance(wanted, dict) else {}
            if CACHE_HANDSHAKE in text or aliases:
                found.append((name, text, aliases))
    return found


def cache_aliases(styles: list[tuple[str, str, dict[str, str]]]) -> dict[str, list[str]]:
    """{protocol name: the aliases the participating packages gave it}."""
    merged: dict[str, list[str]] = {key: [] for key in CACHE_ALIAS_KEYS}
    for _, _, aliases in styles:
        for key, value in aliases.items():
            if value not in merged[key]:
                merged[key].append(value)
    return merged


@lru_cache(maxsize=None)
def user_tex_trees() -> tuple[Path, ...]:
    """The user's own TeX trees (TEXMFHOME, TEXMFLOCAL). A plot job reads files there that
    TeX Live's package database does not cover: nulabreport's vendored chemfig, its
    chemicals.tex."""
    kpsewhich = core.which("kpsewhich")
    if not kpsewhich:
        return ()
    trees: list[Path] = []
    for variable in ("TEXMFHOME", "TEXMFLOCAL"):
        done = core.run_probe([kpsewhich, "-var-value", variable])
        value = done.stdout if done else ""
        for item in re.split(r"[,;{}]", value.strip()):      # a {a,b} list, rarely
            item = item.strip().lstrip("!")
            if item and Path(item).expanduser().is_dir():
                tree = Path(os.path.abspath(Path(item).expanduser()))
                if tree not in trees:
                    trees.append(tree)
    return tuple(trees)


PLOT_KEY_TITLE_RE = re.compile(r"\\title\{|pdftitle=\{")


def plot_key_text(preamble: str) -> str:
    """The preamble as the plot directory's key reads it: without the title (`\\title{...}`,
    hyperref's `pdftitle={...}`) and with every run of white space one space. A part built
    alone has the same settings as the whole document but not its title: nulabreport's
    filter drops the title page of a part (`pdfmd-partial`), and Pandoc wraps the PDF
    title's line differently. Neither draws anything in a plot."""
    kept, position = [], 0
    for match in PLOT_KEY_TITLE_RE.finditer(preamble):
        if match.start() < position:
            continue
        kept.append(preamble[position:match.start()])
        depth, end = 1, match.end()
        while end < len(preamble) and depth:
            if preamble[end - 1] != "\\":
                depth += {"{": 1, "}": -1}.get(preamble[end], 0)
            end += 1
        position = end + 1 if preamble[end:end + 1] == "," else end
    kept.append(preamble[position:])
    return " ".join("".join(kept).split())


def plot_cache_directory(preamble: str, sty_text: str, engine: str, root: Path | None = None) -> Path:
    digest = hashlib.sha1("\0".join([PLOT_CACHE_FORMAT, plot_key_text(preamble), sty_text, core.engine_version_line(engine),
                                     core.tex_tree_stamp()]).encode("utf-8")).hexdigest()[:12]
    return (root or core.cache_root()) / f"plots-{digest}"


def prune_plot_directories(keep: Path) -> None:
    """Keep the newest few plot directories; an older environment (a package or
    preamble from before a change) is never read again."""
    others = sorted((d for d in keep.parent.glob("plots-*") if d.is_dir() and d != keep),
                    key=lambda d: d.stat().st_mtime, reverse=True)
    for stale in others[PLOT_CACHE_KEEP_DIRS - 1:]:
        shutil.rmtree(stale, ignore_errors=True)


def validate_plot_entries(plot_dir: Path, verbose: bool, roots: list[Path] | None = None) -> int:
    """Drop every entry whose recorded input files changed or vanished. Entries record the folders
    they were made in: when the document has moved, the inputs are looked for in the same places
    under the new folders (and the entry keeps working)."""
    import json
    dropped = 0
    current = [str(root) for root in roots] if roots else None
    digests: dict[str, str | None] = {}        # every entry lists the package's own files: hash each once

    def digest_of(name: str) -> str | None:
        if name not in digests:
            digests[name] = core.sha1_file(Path(name))
        return digests[name]

    for deps_file in plot_dir.glob("*.deps"):
        key = deps_file.stem
        try:
            deps = json.loads(deps_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            deps = None
        moved = False
        if isinstance(deps, dict):
            recorded = deps.pop("__roots__", None)
            if current and recorded and recorded != current:
                remapped = {}
                for name, digest in deps.items():
                    for old, new in zip(recorded, current):
                        if name.startswith(old + os.sep):
                            name = new + name[len(old):]
                            break
                    remapped[name] = digest
                deps, moved = remapped, True
        if deps is None or any(digest_of(name) != digest for name, digest in deps.items()):
            for suffix in (".deps", ".dim", ".pdf"):
                (plot_dir / f"{key}{suffix}").unlink(missing_ok=True)
            dropped += 1
            core.vprint(verbose, f"AUTO CACHE  plot {key[:8]}: an input changed; dropped")
        elif moved:
            try:
                deps_file.write_text(json.dumps({**deps, "__roots__": current}), encoding="utf-8")
            except OSError:
                pass
    return dropped


def read_plot_requests(path: Path) -> dict[str, tuple[str, str, str]]:
    requests: dict[str, tuple[str, str, str]] = {}
    if not path.exists():
        return requests
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(PLOT_REQUEST_SEP)
        if len(parts) == 4 and re.fullmatch(r"[0-9a-f]{32}", parts[0]):
            requests[parts[0]] = (parts[1], parts[2], parts[3])
    return requests
