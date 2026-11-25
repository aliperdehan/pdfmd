"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_edit.command`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported.

The commands around the editor (the editor itself is the package's `__init__`): `pdfmd --edit` (`edit_command`; a PDF that
carries its source is `edit_pdf_command`, with `editor_command`, `tree_stamp`, `put_outside_blocks`, `source_carried`,
`source_lost` and `deliver_edited_pdf`) and `pdfmd --init-vscode` (`init_vscode_command`, `VSCODE_TASKS`); and three helpers
of the build's stamp and history that sat beside them in pdfmd.py, `gather_stamp_texts`, `stamp_scope_matches` and
`part_digests`, which pdfmd.py and lib/pdfmd_report call through stand-ins. A rebuild or a watch runs pdfmd.py itself,
`core.__file__`."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path, PurePosixPath

from pdfmd_base import core
from pdfmd_log import emit


VSCODE_TASKS = """{
  // Written by `pdfmd --init-vscode`. Run with Terminal > Run Build Task (Cmd/Ctrl+Shift+B).
  "version": "2.0.0",
  "tasks": [
    {
      "label": "pdfmd: build",
      "type": "shell",
      "command": "pdfmd",
      "args": ["${file}"],
      "group": {"kind": "build", "isDefault": true},
      "presentation": {"reveal": "silent", "panel": "shared"},
      "problemMatcher": []
    },
    {
      "label": "pdfmd: build and open",
      "type": "shell",
      "command": "pdfmd",
      "args": ["${file}", "--open"],
      "group": "build",
      "presentation": {"reveal": "silent", "panel": "shared"},
      "problemMatcher": []
    },
    {
      "label": "pdfmd: watch",
      "type": "shell",
      "command": "pdfmd",
      "args": ["-w", "${file}"],
      "isBackground": true,
      "group": "build",
      "problemMatcher": []
    },
    {
      "label": "pdfmd: check",
      "type": "shell",
      "command": "pdfmd",
      "args": ["--check", "${file}"],
      "presentation": {"reveal": "never", "panel": "shared"},
      "problemMatcher": {
        "owner": "pdfmd-check",
        "fileLocation": ["relative", "${workspaceFolder}"],
        "pattern": {"regexp": "^(.+?):(\\\\d+): (error|warning): (.*)$", "file": 1, "line": 2, "severity": 3, "message": 4}
      }
    },
    {
      "label": "pdfmd: extract tables",
      "type": "shell",
      "command": "pdfmd",
      "args": ["--extract-tables", "${file}"],
      "problemMatcher": []
    },
    {
      "label": "pdfmd: fix tables",
      "type": "shell",
      "command": "pdfmd",
      "args": ["--fix-tables", "${file}"],
      "problemMatcher": []
    }
  ]
}
"""


def init_vscode_command(args) -> int:
    """`pdfmd --init-vscode`: a .vscode/tasks.json with pdfmd tasks, in the current folder; never overwrites one."""
    target = Path.cwd() / ".vscode" / "tasks.json"
    if target.exists():
        emit("note", None, f"NOTE  {core.display_path(target)} exists; nothing was written. The tasks to add:\n{VSCODE_TASKS}")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    core.atomic_write_text(target, VSCODE_TASKS)
    print(f"WROTE  {core.display_path(target)}: tasks pdfmd: build, build and open, watch, extract tables, fix tables "
          "(Terminal > Run Build Task). For commands, history and more, install the extension from the repository's vscode/ folder.")
    return 0


def editor_command(args) -> list[str] | None:
    """The external editor of `--editor CMD` (or `options.editor`), as a command; None for the built-in one."""
    value = args.editor if args.editor is not None else core.config_options().get("editor")
    if value is None or not str(value).strip():
        return None
    try:
        return core.split_command(str(value))
    except ValueError as error:
        raise SystemExit(f"--editor {value!r}: {error}")


def tree_stamp(folder: Path, ignore: set[Path]) -> dict[str, float]:
    """The modification times of the files under ``folder`` (what a watch compares), leaving ``ignore`` out."""
    stamp: dict[str, float] = {}
    for item in folder.rglob("*"):
        try:
            # a hidden file or folder (.backups, .cache) is what a build writes beside the source, not an edit
            if item.is_file() and item not in ignore and not any(part.startswith(".") for part in item.relative_to(folder).parts):
                stamp[str(item)] = item.stat().st_mtime_ns
        except (OSError, ValueError):
            pass
    return stamp


def deliver_edited_pdf(built: Path, pdf: Path) -> Path:
    """Put the rebuilt PDF in place of ``pdf``, keeping the old one in `.backups/` beside it; the new file is written
    beside it first and renamed over it, so a failure leaves the old PDF as it was. Returns the backup."""
    folder = pdf.parent / ".backups"
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / f"{pdf.stem}.{datetime.now().strftime('%Y%m%d-%H%M%S')}{pdf.suffix}"
    shutil.copy2(pdf, backup)
    staged = pdf.with_name(f".{pdf.name}.edit.tmp")
    shutil.copy2(built, staged)
    os.replace(staged, pdf)
    return backup


def edit_pdf_command(args, pdf: Path, passed: list[str]) -> int:
    """`pdfmd --edit FILE.pdf` (v3.28.23): a PDF that carries its source, edited and rebuilt in place. The source is
    restored into a temporary folder; the built-in editor (Ctrl-B builds there) or the `--editor CMD` you name (the
    folder is watched, and rebuilt on every save) works on it; when you leave, the PDF is replaced by the rebuilt one
    (the old one goes to `.backups/`), carrying the source again. The options of the original build are the ones the
    document and its metadata files record; the command-line ones are the ones you give now. A document is edited as the one
    file its source is (v3.28.40: the metadata, preamble, text files, bibliography and style inside it); a -r book as its chapters."""
    if core.pypdf is None:
        emit("error", None, "ERROR  --edit on a PDF needs pypdf (pip install pypdf).", file=sys.stderr)
        return 1
    pdf = pdf.resolve()
    try:
        attachments = core.read_pdf_attachments(pdf)
    except Exception as error:  # noqa: BLE001
        emit("error", None, f"ERROR  {core.display_path(pdf)}: not readable as a PDF ({error})", file=sys.stderr)
        return 1
    if core.ATTACH_MANIFEST not in attachments:
        emit("error", None, f"ERROR  {core.display_path(pdf)} carries no pdfmd source, so there is nothing to edit "
              "(pdfmd --check-source says which PDFs do; build with --attach-source)", file=sys.stderr)
        return 1
    external = editor_command(args)
    if external is None:
        try:
            import pdfmd_edit
        except ImportError:
            emit("error", None, "ERROR  --edit needs the pdfmd_edit package (a full install of pdfmd-cli).", file=sys.stderr)
            return 1
        if not pdfmd_edit.available():
            emit("error", None, "ERROR  --edit needs prompt_toolkit (pdfmd --install tui), or name an editor: --editor \"code --wait\"",
                  file=sys.stderr)
            return 1
    work = Path(tempfile.mkdtemp(prefix="pdfmd-edit-"))
    try:
        folder = work / "source"
        manifest = json.loads(attachments[core.ATTACH_MANIFEST].decode("utf-8"))
        single = manifest.get("mode") != "report"
        # one document: the source as the ONE file it is (metadata, preamble, text files, bibliography and style inside it);
        # a report is its chapters, edited as files (v3.28.40)
        if core.restore_from_pdf(pdf, folder, single=single) != 0:
            return 1
        if single:
            unknown = [block["name"] for block in core.parse_embedded_blocks(attachments[manifest.get("source", core.ATTACH_SOURCE)]
                                                                         .decode("utf-8"))
                       if block["type"] == "lua-filter" and block["sha256"] not in core.trusted_hashes()]
            if unknown and "--trust-embedded" not in passed:
                emit("note", None, f"NOTE  the source embeds the Lua filter {', '.join(unknown)}, which this machine's pdfmd has not "
                      "written: a build skips it unless you add --trust-embedded (read it first)")
        chapters: list[Path] = []
        with core.restore_chain(manifest):
            main_where = core.restore_target_name(str(manifest.get("name") or ""))
            chapter_where = [core.restore_target_name(str(chunk.get("path") or "")) for chunk in manifest.get("chunks") or []]
        if manifest.get("mode") == "report":
            # a -r report is its chapters, in the order it was built: edit and rebuild them all as a report
            # (v3.28.31; before, the first chunk was built alone and replaced the whole book)
            for where in chapter_where:
                if where is not None and (folder / where).is_file():
                    chapters.append(folder / where)
            if not chapters:
                emit("error", None, "ERROR  the restored folder has none of the report's chapters.", file=sys.stderr)
                return 1
            document = chapters[0]
            made = work / pdf.name
        else:
            document = folder / (main_where or PurePosixPath(""))
            if not document.is_file():
                found = sorted(folder.rglob("*.md"))
                if not found:
                    emit("error", None, "ERROR  the restored folder has no Markdown file to edit.", file=sys.stderr)
                    return 1
                document = found[0]
            made = document.with_suffix(".pdf")
        edited = chapters or [document]
        state = {"built": None, "ok": False}

        def digest() -> str:
            return hashlib.sha256(b"\0".join(item.read_bytes() for item in edited)).hexdigest()

        original = digest()

        def build(path: Path):
            if single:
                put_outside_blocks(document, folder, manifest)
            command = ([sys.executable, str(Path(core.__file__).resolve()), *passed, "-r", *map(str, chapters),
                        "--attach-source", "--rewrite", "-o", str(made)] if chapters else
                       [sys.executable, str(Path(core.__file__).resolve()), *passed, "--attach-source", "--rewrite", str(path)])
            done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  cwd=path.parent)
            state["built"], state["ok"] = digest(), done.returncode == 0 and made.exists()
            return state["ok"], (done.stdout + done.stderr).strip(), made if state["ok"] else None

        if external is None:
            import pdfmd_edit
            if len(chapters) > 1:
                emit("note", None, f"NOTE  a report of {len(chapters)} chapters: the built-in editor opens the first, "
                      f"{chapters[0].name}; --editor CMD opens them all ({', '.join(item.name for item in chapters[1:])})")
            pdfmd_edit.run(document, build=build, opener=core.open_file)
        else:
            print(f"EDIT      {shlex.join(external)} {' '.join(item.name for item in edited)}   (the folder is watched: "
                  "every save rebuilds; Ctrl+C, or quitting the editor, finishes)")
            process = subprocess.Popen([*external, *map(str, edited)])
            started = time.monotonic()
            seen = tree_stamp(folder, {made})
            try:
                while True:
                    time.sleep(core.WATCH_INTERVAL)
                    if process.poll() is not None and time.monotonic() - started > 3:
                        break                                    # the editor ended (one that hands over at once keeps us here)
                    if tree_stamp(folder, {made}) != seen:
                        ok, said, _ = build(document)
                        seen = tree_stamp(folder, {made})            # what the build itself wrote is not a new edit
                        print(f"{'BUILT' if ok else 'FAILED':<9} {made.name}" + ("" if ok else "\n" + said[-600:]))
            except KeyboardInterrupt:
                print()
        if digest() == original:
            print("No change: the PDF is as it was.")
            return 0
        if state["built"] != digest():
            ok, said, _ = build(document)                         # edited after the last build
            if not ok:
                emit("error", None, f"ERROR  the last version does not build; {core.display_path(pdf)} is as it was.\n{said[-800:]}",
                      file=sys.stderr)
                return 1
        elif not state["ok"]:
            emit("error", None, f"ERROR  the last build failed; {core.display_path(pdf)} is as it was.", file=sys.stderr)
            return 1
        lost = source_lost(attachments, made)
        if lost is not None and not lost.startswith("lost:"):
            emit("error", None, f"ERROR  {lost}; {core.display_path(pdf)} is as it was.", file=sys.stderr)
            return 1
        if lost:
            emit("warning", None, f"WARN  the rebuilt PDF no longer carries {lost[5:].strip()} (nothing in the text points at "
                  f"{'it' if ',' not in lost else 'them'} now?)", file=sys.stderr)
        if sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get("PDFMD_NO_PROMPT"):
            try:
                answer = input(f"Replace {pdf.name} with the rebuilt one (the old one goes to .backups/)? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer in ("n", "no"):
                kept = pdf.with_name(f"{pdf.stem}.edited{pdf.suffix}")
                shutil.copy2(made, kept)
                print(f"SAVED     {kept.name}  ({pdf.name} was not changed)")
                return 0
        backup = deliver_edited_pdf(made, pdf)
        print(f"REPLACED  {pdf.name}  (rebuilt with its source; the old one: {core.display_path(backup)})")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def put_outside_blocks(document: Path, folder: Path, manifest: dict) -> list[str]:
    """For --edit of a single file: write the text files the source holds for folders above the document's
    (`../schemes/x.tex`) where the document reads them, in the edit's own folder, from what the file says now. A build reads
    them from there (a TeX search does not look above the working folder), so an edit of the block is the edit of the file."""
    try:
        text = document.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    written: list[str] = []
    with core.restore_chain(manifest):
        for block in core.parse_embedded_blocks(core.strip_location_markers(text)):
            if block["type"] != "file":
                continue
            data = block["bytes"] if block.get("bytes") is not None else block["source"].encode("utf-8")
            for place in [block["path"] or block["name"], *block.get("also", [])]:
                where = core.restore_target_name(place) if core.outside_folder(place) else None
                if where is None:
                    continue
                target = folder / where
                if not target.is_file() or target.read_bytes() != data:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    core.atomic_write_bytes(target, data)
                    written.append(place)
    return written


def source_carried(attachments: dict[str, bytes]) -> set[str]:
    """What a PDF's attached source carries, by name: its files (attachments and the text files held as blocks of its text)
    and the embedded data blocks (bibliography, style, filters, history)."""
    manifest = json.loads(attachments[core.ATTACH_MANIFEST].decode("utf-8"))
    names = {name[len(core.EXTRA_PREFIX):] for name in attachments if name.startswith(core.EXTRA_PREFIX)}
    names |= {item["path"] for item in manifest.get("extras") or [] if item.get("inline")}
    text = attachments.get(manifest.get("source", core.ATTACH_SOURCE), b"").decode("utf-8", errors="replace")
    names |= {block["path"] or block["name"] for block in core.parse_embedded_blocks(text) if block["type"] != "file"}
    return {name.replace("__up__", "..") for name in names}


def source_lost(before: dict[str, bytes], rebuilt: Path) -> str | None:
    """None when the rebuilt PDF carries its source and everything the old one carried; "lost: a, b" for what it no
    longer carries; else the reason it carries no source."""
    try:
        after = core.read_pdf_attachments(rebuilt)
    except Exception as error:  # noqa: BLE001
        return f"the rebuilt PDF cannot be read ({error})"
    if core.ATTACH_MANIFEST not in after or core.ATTACH_SOURCE not in after:
        return "the rebuilt PDF does not carry its source"
    lost = sorted(source_carried(before) - source_carried(after))
    return f"lost: {', '.join(lost[:6])}{' and %d more' % (len(lost) - 6) if len(lost) > 6 else ''}" if lost else None


def edit_command(args) -> int:
    """`pdfmd --edit [FILE]`: the small full-screen editor (pdfmd_edit), building with the options given beside it.
    With a PDF that carries its source, or with `--editor CMD`, see edit_pdf_command / the watch below."""
    given = {str(item) for item in args.path or []}
    passed = [item for item in sys.argv[1:] if item != "--edit" and item not in given]
    if args.editor is not None:
        passed = [item for index, item in enumerate(passed) if item != "--editor" and item != args.editor
                  and not item.startswith("--editor=")]
    if len(args.path or []) == 1 and args.path[0].suffix.lower() == ".pdf":
        return edit_pdf_command(args, args.path[0], passed)
    external = editor_command(args)
    try:
        import pdfmd_edit
    except ImportError:
        emit("error", None, "ERROR  --edit needs the pdfmd_edit package (a full install of pdfmd-cli).", file=sys.stderr)
        return 1
    if external is None and not pdfmd_edit.available():
        emit("error", None, "ERROR  --edit needs prompt_toolkit: run `pdfmd --install tui`.", file=sys.stderr)
        return 1
    if len(args.path or []) > 1:
        emit("error", None, "ERROR  --edit opens one file.", file=sys.stderr)
        return 1
    target = (args.path or [Path.cwd()])[0]
    try:
        document = core.find_markdown(target)
    except FileNotFoundError as error:
        if target.suffix.lower() in (".md", ".markdown") and not target.is_dir():
            document = target.resolve()                 # a new file, made when it is first saved
        else:
            emit("error", None, f"ERROR  {error}", file=sys.stderr)
            return 1

    def build(path: Path):
        done = subprocess.run([sys.executable, str(Path(core.__file__).resolve()), *passed, "--rewrite", str(path)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=path.parent)
        made = path.with_suffix(".pdf")
        return done.returncode == 0, (done.stdout + done.stderr).strip(), made if done.returncode == 0 and made.exists() else None

    if external is not None:
        # an editor of your own on a Markdown file: pdfmd -w beside it (rebuild on every save) until it is closed
        process = subprocess.Popen([*external, str(document)])
        watcher = subprocess.Popen([sys.executable, str(Path(core.__file__).resolve()), *passed, "--watch", str(document)],
                                   cwd=document.parent)
        try:
            while True:
                time.sleep(core.WATCH_INTERVAL)
                if process.poll() is not None and watcher.poll() is None:
                    time.sleep(3)
                    if process.poll() is not None:
                        break
                if watcher.poll() is not None:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            watcher.terminate()
        return 0
    return pdfmd_edit.run(document, build=build, opener=core.open_file)


def gather_stamp_texts(md_path: Path, preamble_files: list[Path]) -> list[str]:
    """Raw LaTeX text stamp_summary checks for \\usepackage{...}: a
    document's discovered preambles plus its own header-includes block.
    """
    texts = [preamble.read_text(encoding="utf-8-sig") for preamble in preamble_files]
    texts.append(core.document_header_includes(md_path.read_text(encoding="utf-8-sig")) or "")
    return texts


def stamp_scope_matches(options: dict, report_output: Path | None) -> bool:
    """Whether options['scope'] allows stamping in this context -- shared by
    the pre-compile PDF-metadata path and the post-compile .md-stamp path,
    so both always agree on when to fire (see DEFAULT_STAMP_OPTIONS).
    """
    wanted_scope = "report" if report_output is not None else "standalone"
    return options["scope"] in ("always", wanted_scope)


def part_digests(parts: list[Path], root: Path | None) -> list[tuple[str, str]]:
    """(name, digest) of each part of a document in parts: its path under the parts folder without `.md`, spaces as `_`
    (a .hst word has none), and the first 8 characters of the hash of its text -- what the history compares."""
    found: list[tuple[str, str]] = []
    for part in parts:
        try:
            label = str(part.relative_to(root)) if root else part.name
        except ValueError:
            label = part.name
        try:
            digest = core.sha256_text(core.normalized_source(part.read_text(encoding="utf-8-sig")))[:8]
        except (OSError, UnicodeDecodeError):
            digest = ""
        found.append((re.sub(r"\s+", "_", label.removesuffix(".md")), digest))
    return found
