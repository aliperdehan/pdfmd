"""Restoring the source a PDF (or a Markdown file) carries: `--restore`, `--check-source` and the layout it writes back.

Moved out of `pdfmd.py` unchanged (v3.33.29, SPLIT.md), with `RESTORE_CHAIN`. `core` is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first
binding wins); the pdfmd names the code uses are read as `core.X` when it runs, and so is `core.pypdf`, a lazy loader there, so pypdf is never imported at
the top here. `VERBOSE_OUTPUT` is rebound by `main` and patched by tests, so it stays in `pdfmd.py` and is read as `core.VERBOSE_OUTPUT`.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import posixpath
import re
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from tempfile import mkdtemp

try:
    import yaml
except ImportError:
    yaml = None

from pdfmd_pdfimages import extract_pdf_images, rewrite_image_paths, rewrite_tex_image_paths

core = None


def folder_counts(names: list[str]) -> str:
    """File names counted by their first folder: ``report.md, metadata/ 5, ir/ 24`` (the files of the top
    level by name, up to three, else counted)."""
    top = [name for name in names if "/" not in name]
    folders: dict[str, int] = {}
    for name in names:
        if "/" in name:
            folders[name.split("/", 1)[0]] = folders.get(name.split("/", 1)[0], 0) + 1
    shown = top if len(top) <= 3 else [f"{len(top)} files"]
    return ", ".join([*shown, *(f"{folder}/ {count}" for folder, count in folders.items())])


def restored_image_paths(name: str, content: "str | bytes", renamed: dict[str, str]) -> "str | bytes":
    """A restored file's content with the image paths in ``renamed`` updated: Markdown text, and the .tex a bundle stored."""
    lower = name.lower()
    if isinstance(content, str) and lower.endswith((".md", ".markdown")):
        return rewrite_image_paths(content, renamed)
    if isinstance(content, bytes) and lower.endswith(".tex"):
        try:
            folder = str(PurePosixPath(name).parent) if "/" in name else ""
            return rewrite_tex_image_paths(content.decode("utf-8"), renamed, folder).encode("utf-8")
        except UnicodeDecodeError:
            return content
    return content


RESTORE_CHAIN: list[str] = []      # the folders from the one a restore writes into down to the document's (manifest "chain")


@contextmanager
def restore_chain(manifest: dict) -> Iterator[None]:
    """While active, restore_target_name places a manifest path under the document's own folder, which sits ``chain``
    below the folder a restore writes into: a source whose files are in sibling folders (`../schemes/x.tex`) comes back as
    `schemes/x.tex` beside `<folder>/document.md`."""
    saved = list(RESTORE_CHAIN)
    chain = manifest.get("chain")
    RESTORE_CHAIN[:] = [str(item) for item in chain] if isinstance(chain, list) else []
    try:
        yield
    finally:
        RESTORE_CHAIN[:] = saved


def restore_target_name(name: str) -> PurePosixPath | None:
    """A path read from a PDF's manifest, safe to write under the target folder, or None."""
    if RESTORE_CHAIN:
        joined = posixpath.normpath(posixpath.join(*RESTORE_CHAIN, name.replace("\\", "/")))
        name = joined if not joined.startswith("..") else ""
    path = PurePosixPath(name.replace("\\", "/"))
    if not path.parts or path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", path.parts[0]):
        return None
    return path


def check_source_command(paths: list[Path], recursive: bool = False) -> bool:
    """`--check-source [PDF or FOLDER ...]` (v3.28.22): which PDFs carry their source, read from the attachment list alone,
    without building anything. A folder means the PDFs in it (all below it with --recursive); no argument, the working
    folder. True when every PDF does."""
    if core.pypdf is None:
        print("--check-source needs pypdf (pip install pypdf)", file=sys.stderr)
        return False
    pdfs: list[Path] = []
    for path in (paths or [Path.cwd()]):
        if path.is_dir():
            pdfs += sorted((path.rglob("*.pdf") if recursive else path.glob("*.pdf")), key=lambda item: core.natural_key(item.name))
        elif path.suffix.lower() == ".pdf" and path.is_file():
            pdfs.append(path)
        else:
            print(f"WARN  {core.display_path(path)}: not a PDF or a folder", file=sys.stderr)
    carrying = 0
    missing: list[str] = []
    for pdf in pdfs:
        name = core.display_path(pdf)
        try:
            attachments = core.read_pdf_attachments(pdf)
        except Exception as error:  # noqa: BLE001
            print(f"{'ERROR':<9} {name}  not readable as a PDF ({str(error)[:60]})")
            missing.append(name)
            continue
        beside = [pdf.with_suffix(suffix) for suffix in (".md", ".markdown", ".qmd") if pdf.with_suffix(suffix).is_file()]
        if core.ATTACH_MANIFEST in attachments:
            try:
                manifest = json.loads(attachments[core.ATTACH_MANIFEST].decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                manifest = {}
            text = attachments.get(manifest.get("source") or core.ATTACH_SOURCE)
            facts = [str(manifest.get("name") or "source")]
            if text is not None:
                facts.append(f"{text.decode('utf-8', errors='replace').count(chr(10))} lines")
                if manifest.get("sha256") and core.sha256_text(text.decode("utf-8", errors="replace")) != manifest["sha256"]:
                    facts.append("the attached text was edited after the build")
            if manifest.get("pdfmd"):
                facts.append(f"pdfmd {manifest['pdfmd']}")
            newer = [item.name for item in beside if item.stat().st_mtime > pdf.stat().st_mtime + 1]
            if newer:
                facts.append(f"{newer[0]} beside it is newer")
            print(f"{'SOURCE':<9} {name}  " + ", ".join(facts))
            carrying += 1
            continue
        odf = next((item for item in sorted(attachments) if item.startswith("Original.") and item[9:] in core.HYBRID_MIME), None)
        if odf is not None:
            print(f"{'HYBRID':<9} {name}  carries {odf} (LibreOffice opens this PDF as it)")
            carrying += 1
            continue
        missing.append(name)
        hint = (f"{beside[0].name} is beside it: pdfmd {beside[0].name} --attach-source" if beside
                else f"no {pdf.stem}.md beside it")
        print(f"{'NONE':<9} {name}  {hint}")
    if not pdfs:
        print("No PDF here.")
        return True
    total = f"{len(pdfs)} PDF{'s' if len(pdfs) != 1 else ''}"
    print(f"CHECK     {total}: {carrying} with the source" + (f", {len(missing)} without" if missing else ""))
    return not missing


def restore_from_pdf(pdf_path: Path, out_dir: Path | None, list_only: bool = False, single: bool = False) -> int:
    """--restore: write back the layout a PDF's attached source records. Never
    overwrites (it stops, writing nothing, if a file is already there). Exit
    status 1 if the attached text no longer matches its recorded hash."""
    if core.pypdf is None:
        raise SystemExit("--restore needs pypdf (pip install pypdf)")
    if not pdf_path.is_file():
        raise SystemExit(f"{pdf_path}: no such file")
    try:
        attachments = core.read_pdf_attachments(pdf_path)
    except Exception as error:  # noqa: BLE001
        raise SystemExit(f"{core.display_path(pdf_path)}: not readable as a PDF ({error})")
    odf_name = next((name for name in sorted(attachments)
                     if name.startswith("Original.") and name[9:] in core.HYBRID_MIME), None)
    if core.ATTACH_MANIFEST not in attachments:
        if odf_name is not None:
            # a hybrid PDF (LibreOffice's, or pdfmd --hybrid) with no pdfmd source: the editable copy is what it holds
            target = (out_dir or pdf_path.with_name(f"{pdf_path.stem}{core.RESTORED_SUFFIX}")).resolve()
            destination = target / f"{pdf_path.stem}.{odf_name[9:]}"
            print(f"ODF       {odf_name}  ({len(attachments[odf_name])} bytes; LibreOffice opens this PDF as it)")
            if list_only:
                return 0
            if destination.exists():
                raise SystemExit(f"{core.display_path(destination)} already exists; nothing was written "
                                 "(remove it, or give another -o folder)")
            destination.parent.mkdir(parents=True, exist_ok=True)
            core.atomic_write_bytes(destination, attachments[odf_name])
            print(f"RESTORED  {destination.name}  (the OpenDocument file the PDF carries)")
            return 0
        names = ", ".join(sorted(attachments)) or "no attachments at all"
        raise SystemExit(f"{core.display_path(pdf_path)} carries no pdfmd source ({names}); "
                         "build it with --attach-source or pdfmd-options.attach-source")
    return restore_attachments(pdf_path, attachments, out_dir, list_only, odf_name, single)


def restore_attachments(pdf_path: Path, attachments: dict[str, bytes], out_dir: Path | None, list_only: bool,
                        odf_name: str | None = None, single: bool = False) -> int:
    """The part of --restore that does not care where the source came from: a PDF's attachments or a Markdown file's
    kept source (``pdf_path`` is that file). ``single``: the source as the one file it is (`--edit`), not split back
    into the files it was made from: the text with its embedded metadata, preamble, text files, bibliography and style,
    and beside it the files that are not part of the text (a package, files in sibling folders, pictures)."""
    with restore_chain(json.loads(attachments[core.ATTACH_MANIFEST].decode("utf-8"))):
        return restore_attachments_in_place(pdf_path, attachments, out_dir, list_only, odf_name, single)


def restore_attachments_in_place(pdf_path: Path, attachments: dict[str, bytes], out_dir: Path | None, list_only: bool,
                                 odf_name: str | None = None, single: bool = False) -> int:
    manifest = json.loads(attachments[core.ATTACH_MANIFEST].decode("utf-8"))
    if manifest.get("format", 0) > core.ATTACH_FORMAT:
        raise SystemExit(f"{core.display_path(pdf_path)} was made by a newer pdfmd (pdfmd {manifest.get('pdfmd', '?')}, attachment "
                         f"format {manifest.get('format')}; this pdfmd {core.PDFMD_VERSION} reads up to {core.ATTACH_FORMAT}); "
                         "upgrade pdfmd to restore it")
    is_pdf = pdf_path.suffix.lower() == ".pdf"
    merged = attachments.get(manifest.get("source", core.ATTACH_SOURCE), b"").decode("utf-8")
    status = 0
    if core.sha256_text(merged) != manifest.get("sha256"):
        print("WARN  the attached source does not match its recorded hash (edited since it was attached)",
              file=sys.stderr)
        status = 1
    chunks = manifest.get("chunks") or []
    print(f"SOURCE    {manifest.get('name', '?')}  (pdfmd {manifest.get('pdfmd', '?')}, "
          f"{len(chunks)} file{'s' if len(chunks) != 1 else ''}, "
          f"{core.comments_note(manifest)})")
    for line in manifest.get("bibliography") or []:
        print(f"          bibliography {line}")
    if manifest.get("csl_left"):
        print(f"NOTE  the citation style {', '.join(manifest['csl_left'])} is not in the source (--attach-csl carries it): "
              "a build needs a style of that name (Pandoc's own csl/ folder, or beside the document)")
    # The files are counted by folder unless --verbose or --list asks for each (v3.28.15)
    compact = not core.VERBOSE_OUTPUT and not list_only
    for line in core.requirement_lines(manifest):
        if not (compact and line.startswith("MADE WITH")):
            print(line)
    extras = manifest.get("extras") or []
    stored = {item["path"] for item in extras}
    absent: list[str] = []
    for image in manifest.get("images") or []:
        if image["path"] not in stored:
            from_pdf = bool(image.get("pdf") and is_pdf)
            if compact and not from_pdf:
                absent.append(image["path"])
            elif not compact:
                print(f"IMAGE     {image['path']}  ("
                      + ("taken out of the PDF's own picture" if from_pdf
                         else "recorded, not in the PDF" if is_pdf else "recorded, not stored in the Markdown") + ")")
    if absent:
        print(f"IMAGE     {len(absent)} not in the PDF" + ("" if is_pdf else " or the Markdown")
              + f" (put the file{'s' if len(absent) != 1 else ''} back beside the document if the build needs "
              f"{'them' if len(absent) != 1 else 'it'}): " + ", ".join(absent[:3])
              + (f" and {len(absent) - 3} more (--verbose)" if len(absent) > 3 else ""))
    for item in extras:
        if not compact:
            print(f"FILE      {item['path']}  ({item['size']} bytes{', from ' + ('a kit' if item.get('from') == 'kit' else 'a TeX tree') if item.get('from') else ''})")
    if list_only:
        return status
    name = restore_target_name(manifest.get("name", "")) or PurePosixPath("document.md")
    target = (out_dir or pdf_path.with_name(f"{pdf_path.stem}{core.RESTORED_SUFFIX}")).resolve()
    files: dict[str, str | bytes] = ({str(name): core.with_location_markers(merged)} if single else dict(layout_from_source(
        core.strip_location_markers(merged), manifest, name, core.sha256_text(merged) == manifest.get("sha256"))))
    for item in extras:
        if item.get("inline"):
            continue                                  # a block of the text: layout_from_source put it back
        where = restore_target_name(item["path"])
        data = attachments.get(core.extra_key(item["path"]))
        if where is None or data is None:
            print(f"WARN  {item['path']}: {'not a path that can be restored' if where is None else 'missing from the PDF'}; skipped",
                  file=sys.stderr)
            status = 1
            continue
        if hashlib.sha256(data).hexdigest() != item.get("sha256"):
            print(f"WARN  {item['path']} does not match its recorded hash (edited since it was attached)",
                  file=sys.stderr)
            status = 1
        files[str(where)] = data
    if odf_name is not None:
        odf_target = str(name.with_suffix("." + odf_name[9:]))
        if odf_target not in files:
            files[odf_target] = attachments[odf_name]
            print(f"ODF       {odf_name}  (comes back as {odf_target}: the editable copy LibreOffice opens)")
    pictures, renamed, failed = (extract_pdf_images(pdf_path, manifest.get("images") or [], stored)
                                 if is_pdf else ({}, {}, []))
    for name in failed:
        print(f"WARN  {name}: the PDF's picture could not be taken out; put the file back beside the document",
              file=sys.stderr)
    for name, data in pictures.items():
        where = restore_target_name(name)
        if where is not None and str(where) not in files:
            files[str(where)] = data
    for name, new in renamed.items():
        print(f"IMAGE     {name} comes back as {new} (the PDF holds the drawing, not the original file)")
    if renamed:
        files = {name: restored_image_paths(name, content, renamed) for name, content in files.items()}
    layers = (manifest.get("layers") or {}).get("options")
    if layers and not single and yaml is not None:
        settings = f"{core.FOLDER_DIR}/config.yaml"
        if (target / settings).exists():
            own = core.folder_file_data(target / settings) or {}
            own = own.get("options") if isinstance(own.get("options"), dict) else {}
            differ = [f"{key}: {value}" for key, value in layers.items() if own.get(key) != value]
            if differ:
                print(f"NOTE  {settings} is already in {core.display_path(target)} and is kept as it is; the build also used "
                      f"{'; '.join(differ)}")
        else:
            files[settings] = ("# written by pdfmd --restore: the folder settings (the options of the .pdfmd/config.yaml files above\n"
                               "# the report, nearest first) the PDF was built with\n"
                               + yaml.safe_dump({"options": layers}, allow_unicode=True, sort_keys=False))
    clashes = [item for item in files if (target / item).exists()]
    if clashes:
        raise SystemExit(f"{core.display_path(target)} already holds {', '.join(clashes)}; nothing was written "
                         "(remove them, or give another -o folder)")
    for item, content in files.items():
        destination = target / item
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            core.atomic_write_bytes(destination, content)
        else:
            core.write_text_lf(destination, content)
        if not compact:
            print(f"RESTORED  {item}")
    print(f"RESTORED  {len(files)} file{'s' if len(files) != 1 else ''} into {core.display_path(target)}"
          + (f"  ({folder_counts(list(files))}"
             + (f"; {len(pictures)} picture{'s' if len(pictures) != 1 else ''} taken out of the PDF" if pictures else "")
             + ")" if compact else ""))
    if manifest.get("mode") == "report":
        print(f"NOTE  this PDF came from a -r/--report build: `pdfmd -r {core.display_path(target)}` builds it again")
    filters = [item for item in files if item.lower().endswith(".lua")]
    if filters:
        print(f"NOTE  {', '.join(filters)}: a Lua filter is code, and pdfmd runs one that sits beside a "
              "document when it builds -- read it first if the PDF is not from you")
    return status


def restore_from_markdown(path: Path, out_dir: Path | None, list_only: bool = False) -> int:
    """--restore FILE.md: write back the source a Markdown file keeps (--keep-source)."""
    try:
        import pdfmd_flat.keep as keep
    except ImportError:
        raise SystemExit("--restore of a Markdown file needs the pdfmd_flat package (install pdfmd-cli)")
    if not path.is_file():
        raise SystemExit(f"{path}: no such file")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
        body, trailer = keep.split(text)
        if trailer is None:
            raise SystemExit(f"{core.display_path(path)} keeps no pdfmd source; build it with --keep-source "
                             "or pdfmd-options.keep-source")
        attachments = keep.unpack(trailer)
    except keep.KeepError as error:
        raise SystemExit(f"{core.display_path(path)}: {error}")
    except UnicodeDecodeError:
        raise SystemExit(f"{core.display_path(path)} is not a UTF-8 text file")
    if core.ATTACH_MANIFEST not in attachments:
        raise SystemExit(f"{core.display_path(path)}: the kept source has no manifest")
    if trailer.body_hash and keep.digest(body) != trailer.body_hash:
        print("NOTE  the Markdown was edited since pdfmd wrote it; the restored source is what it was made from, "
              "not these edits", file=sys.stderr)
    return restore_attachments(path, attachments, out_dir, list_only)


def restore_front_matter(text: str, manifest: dict, parts_held: bool = False) -> str:
    """The restored document's front matter without the bookkeeping embedding
    added to `pdfmd-options` (what was embedded, and the no-auto kinds that kept
    discovery from finding it again): the document's own no-auto, if it had one.
    ``parts_held``: a restored metadata file says `pdfmd-options.parts` itself."""
    front = re.match(r"^---[ \t]*\n(?P<yaml>.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if not front or yaml is None:
        return text
    try:
        data = yaml.safe_load(front.group("yaml"))
    except yaml.YAMLError:
        return text
    if not isinstance(data, dict):
        return text
    options = data.get("pdfmd-options")
    if not isinstance(options, dict):
        options = data["pdfmd-options"] = {}
    options.pop("embedded", None)
    if manifest.get("parts") and "parts" not in options and not parts_held:
        options["parts"] = manifest["parts"]    # it came from a metadata file, which is not carried
    if "no-auto" in options:
        original = manifest.get("no_auto")
        if original is None:
            options.pop("no-auto")
        else:
            options["no-auto"] = original
    if not options:
        data.pop("pdfmd-options")
    if not data:
        return text[front.end():].lstrip("\n")
    original = manifest.get("front_matter_text")
    if original:
        try:
            if yaml.safe_load(re.sub(r"^---[ \t]*\n|(?:---|\.\.\.)[ \t]*\n?$", "", original)) == data:
                return original.rstrip("\n") + "\n" + text[front.end():]
        except yaml.YAMLError:
            pass
    dumped = yaml.dump(data, Dumper=core._EmbedDumper, sort_keys=False, allow_unicode=True,
                       default_flow_style=False, width=10**6)
    return f"---\n{dumped}---\n" + text[front.end():]


def original_metadata_text(manifest: dict, entry: dict, rebuilt: str, unedited: bool = False) -> str:
    """A metadata file as it was written, with its comments, when the attachment kept its text and either the
    attached source is unedited (its hash matches: the text is the file the build read, v3.28.13) or the rebuilt
    file reads as the same data (else the rebuilt one: the text of a file that has changed meaning is not it)."""
    original = (manifest.get("metadata_texts") or {}).get(entry["path"])
    if original is None or yaml is None or entry.get("kind") != "metadata":
        return rebuilt
    if unedited:
        return original
    try:
        return original if without_parts(yaml.safe_load(original)) == without_parts(yaml.safe_load(rebuilt)) else rebuilt
    except yaml.YAMLError:
        return rebuilt


def without_parts(data):
    """A metadata file's data minus pdfmd-options.parts, which a restore may have moved into the document."""
    if not isinstance(data, dict) or not isinstance(data.get("pdfmd-options"), dict):
        return data
    return {**data, "pdfmd-options": {key: value for key, value in data["pdfmd-options"].items() if key != "parts"}}


def text_holds_parts(text: str) -> bool:
    """Whether a metadata file's text says `pdfmd-options.parts` (so the restored document need not)."""
    if yaml is None:
        return False
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    return isinstance(data, dict) and isinstance(data.get("pdfmd-options"), dict) and "parts" in data["pdfmd-options"]


def is_global_layout_entry(entry: dict) -> bool:
    """Whether a manifest's layout entry is pdfmd's global metadata file (pdfmd --setup): marked since v3.28.13;
    before, it shows as a metadata file outside the document's folder named pdfmd/metadata.yaml."""
    if entry.get("kind") != "metadata":
        return False
    if entry.get("global"):
        return True
    path = PurePosixPath(str(entry.get("path", "")).replace("\\", "/"))
    return (restore_target_name(str(path)) is None and path.name.casefold() == "metadata.yaml"
            and path.parent.name.casefold() == "pdfmd")


def assembled_origin(text: str) -> dict:
    """An assembled text's `pdfmd-options.origin` ({} when it records none)."""
    front = re.match(r"^---[ \t]*\n(?P<yaml>.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if not front or yaml is None:
        return {}
    try:
        data = yaml.safe_load(front.group("yaml"))
    except yaml.YAMLError:
        return {}
    options = data.get("pdfmd-options") if isinstance(data, dict) else None
    origin = options.get("origin") if isinstance(options, dict) else None
    return origin if isinstance(origin, dict) else {}


def layout_from_source(merged: str, manifest: dict, main_name: PurePosixPath,
                       unedited: bool | None = None) -> dict[str, str | bytes]:
    """The files of the original layout, as {relative path: text}, from the
    attached assembled text: --unpack --slim does the splitting of the embedded
    metadata, preamble, filters and bibliography; the manifest says where each
    sat, where a part began, and what a part's own front matter was."""
    origin = assembled_origin(merged)
    work = Path(mkdtemp(prefix="pdfmd-restore-"))
    try:
        assembled = work / "x.md"
        core.write_text_lf(assembled, merged)
        unpacked = work / "x.unpacked"
        with contextlib.redirect_stdout(io.StringIO()):
            core.unpack_assembled(assembled, unpacked, slim=True)
        text = assembled.read_text(encoding="utf-8")
        found = {}
        if unpacked.is_dir():
            for item in sorted(unpacked.rglob("*")):
                if item.is_file():
                    found[item.relative_to(unpacked).as_posix()] = item.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    # the text files the source holds as `type: file` blocks come back at their own paths (not under NAME.unpacked/)
    placed: dict[str, str | bytes] = {}
    block_names: set[str] = set()
    for block in core.parse_embedded_blocks(merged):
        if block["type"] != "file":
            continue
        data = block["bytes"] if block.get("bytes") is not None else block["source"].encode("utf-8")
        for place in [block["path"] or block["name"], *block.get("also", [])]:
            block_names.add(core.block_relative_path(place))
            where = restore_target_name(place)
            if where is not None:
                placed[str(where)] = data
    found = {name: content for name, content in found.items() if name not in block_names}
    layout = [dict(entry) for entry in manifest.get("layout") or []]
    metadata_entries = [entry for entry in layout if entry["kind"] == "metadata"]
    if not metadata_entries:
        found.pop("metadata.yaml", None)       # no metadata file existed: the keys stay in the document
    # The metadata pieces --unpack names after the files' labels, in the order the build listed the files,
    # which is the layout's order too (v3.28.13: a label made unique as `folder-name.yaml` matches as well)
    labels = list(origin.get("files") or {})
    by_label = dict(zip(labels, metadata_entries)) if len(labels) == len(metadata_entries) else {}
    if unedited is None:
        unedited = core.sha256_text(merged) == manifest.get("sha256")
    extras: dict[str, str] = {}
    strays: list[tuple[str, str, dict | None]] = []
    global_keys = (origin.get("files") or {}).get(origin.get("global")) or []
    for name, content in found.items():
        is_yaml = name.lower().endswith((".yaml", ".yml"))
        match = None
        if is_yaml and by_label:
            match = by_label.get(name) or by_label.get(re.sub(r"^\d\d-", "", name))
        if match is None:
            base = PurePosixPath(re.sub(r"^\d\d-", "", PurePosixPath(name).name))
            match = next((entry for entry in layout
                          if PurePosixPath(entry["path"]).name == base.name and not entry.get("used")), None)
        if match is not None and is_global_layout_entry(match):
            # the building machine's global metadata (a PDF made before v3.28.13 carries it as a file):
            # not the document's, and in NAME.unpacked/ it hid the folder's own metadata files
            match["used"] = True
            if not global_keys and yaml is not None:
                try:
                    loaded = yaml.safe_load(content)
                except yaml.YAMLError:
                    loaded = None
                global_keys = list(loaded) if isinstance(loaded, dict) else []
            continue
        if match is not None:
            match["used"] = True
            where = restore_target_name(match["path"])
            content = original_metadata_text(manifest, match, content, unedited)
        elif name in (manifest.get("data_files") or []):
            # A bibliography or CSL file: the metadata names it, and pdfmd looks for it beside
            # the first metadata file (then the document), so it goes there.
            metadata_entry = next((entry for entry in metadata_entries if not is_global_layout_entry(entry)
                                   and restore_target_name(entry["path"])), None)
            folder = PurePosixPath(metadata_entry["path"]).parent if metadata_entry else PurePosixPath(".")
            where = restore_target_name(str(folder / name))
        else:
            where = None
        if where is None and is_yaml:
            strays.append((name, content, match))
            continue
        if match is not None and match["kind"] == "metadata":
            match["restored"] = str(where)
        extras[str(where) if where else f"{main_name.stem}.unpacked/{name}"] = content
    own = [entry for entry in metadata_entries if entry.get("restored")]
    moved: list[str] = []
    for name, content, entry in strays:
        if not own:
            extras[f"{main_name.stem}.unpacked/{name}"] = content    # found there by itself: nothing else to hide
            continue
        # NAME.unpacked/'s YAML is all the metadata a build reads, so there it would hide the folder's own files
        where = "outside/" + re.sub(r"^\d\d-", "", name)
        extras[where] = content
        if entry is not None:
            entry["restored"] = where
        moved.append(where + (f" (was {entry['path']})" if entry is not None else ""))
    if moved:
        order = " ".join(f"-y {item['restored']}" for item in metadata_entries if item.get("restored"))
        print(f"WARN  {', '.join(moved)}: metadata from outside the document's folder, where no build finds it by "
              f"itself; build with {order} to layer it as before", file=sys.stderr)
    if global_keys:
        print(f"NOTE  {', '.join(str(key) for key in global_keys)}: from pdfmd's global metadata (pdfmd --setup) on "
              "the machine that built it; not restored: a build here uses this machine's own")
    # The document itself: the assembled marker is how a build knew the text was
    # finished, so it goes (a restored file is a source again).
    text = core.ASSEMBLED_COMMENT_RE.sub("", text)
    text = re.sub(r"^pdfmd-assembled:[ \t]*(?:true|yes|on)[ \t]*\n", "", text, count=1, flags=re.MULTILINE)
    held = any(text_holds_parts(extras[entry["restored"]]) for entry in own)
    text = restore_front_matter(text.rstrip("\n") + "\n", manifest, held)
    files: dict[str, str] = {}
    chunks = manifest.get("chunks") or []
    if len(chunks) > 1:
        front = re.match(r"^---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
        header = front.group(0) if front else ""
        lines = text[len(header):].splitlines()
        position = 0
        for index, chunk in enumerate(chunks):
            while position < len(lines) and not lines[position].strip():
                position += 1
            piece = "\n".join(lines[position:position + chunk["lines"]]) + "\n"
            position += chunk["lines"]
            if chunk["lines"] == 0:
                piece = ""
            piece = "\n" * chunk.get("lead", 0) + piece
            where = restore_target_name(chunk["path"]) or PurePosixPath(f"part-{index}.md")
            files[str(where)] = (header + piece) if index == 0 else (chunk.get("head", "") + piece)
    else:
        files[str(main_name)] = text
    files.update(extras)
    files.update(placed)
    return files
