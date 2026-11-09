"""Finishing a built PDF with pypdf: bookmarks from the Markdown headings, a running header and footer from a
`left,middle,right` template, and the local files the document links to, attached beside the link (`--bookmarks`,
`--header`, `--footer`, `--attach-links`, `--pdf-title` and the rest).

Moved out of `pdfmd.py` unchanged (v3.33.13, SPLIT.md), with `HF_FIELDS`, `HF_FONT`, `HF_SIZE`, `HF_MARGIN` and
`LINKED_FILE_LIMIT`. `core` is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first binding wins); the pdfmd names the
code uses (`POLISH_CLI`, `add_deflated_attachment`, `atomic_write_pdf`, `display_path`, `fence_after`) are read as `core.X` when it
runs, and so is `core.pypdf`, a lazy loader there, so pypdf is never imported at the top here (the `from pypdf.generic import ...`
lines stay inside the functions, as they were). `polish_pdf` was decorated with `pdfmd`'s `@timed`, which is defined far below the
place where the package loads: `_timed` is the same decorator looked up at call time (`core.timed(name)(function)`).
"""

from __future__ import annotations

import functools
import logging
import re
import sys
import unicodedata
import urllib.parse
import warnings
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:     # only the annotations name it; the code reads core.pypdf
    import pypdf

core = None


def _timed(name):
    """`core.timed(name)` for a function defined before `core.timed` exists: each call is wrapped when it is made."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            return core.timed(name)(function)(*args, **kwargs)
        return wrapper
    return decorate


HF_FIELDS = ("page", "pages", "header", "heading", "date", "title")
HF_FONT, HF_SIZE, HF_MARGIN = "Helvetica", 9.0, 36.0
LINKED_FILE_LIMIT = 25 * 1024 * 1024


def parse_hf_template(text: str) -> tuple[str, str, str]:
    """``"left,middle,right"`` (a comma inside a field is written ``\\,``)."""
    parts = re.split(r"(?<!\\),", text)
    if len(parts) != 3:
        raise ValueError(f"header/footer template {text!r} needs three comma-separated fields "
                         "(left,middle,right); write \\, for a comma inside one")
    left, middle, right = (part.replace("\\,", ",") for part in parts)
    return left, middle, right


def fill_hf_field(template: str, values: dict[str, str]) -> str:
    return re.sub(r"\{(" + "|".join(HF_FIELDS) + r")\}", lambda match: values[match.group(1)], template)


def markdown_headings(texts: list[str]) -> list[tuple[int, str]]:
    """(level, plain text) of the ATX and setext headings in Markdown ``texts``, in order, leaving out
    front matter, fenced code and HTML comments."""
    found: list[tuple[int, str]] = []
    for text in texts:
        text = re.sub(r"\A---\n.*?\n(?:---|\.\.\.)[ \t]*\n", "", text.lstrip("﻿"), count=1, flags=re.S)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        lines = text.splitlines()
        fence = ""
        for index, line in enumerate(lines):
            stripped = line.strip()
            before, fence = fence, core.fence_after(fence, stripped)
            if before or fence:
                continue
            level, title = 0, ""
            atx = re.match(r"\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$", line)
            if atx:
                level, title = len(atx.group(1)), atx.group(2)
            elif (index and re.fullmatch(r"\s{0,3}(=+|-+)\s*", line) and stripped
                  and lines[index - 1].strip() and not re.match(r"\s*(#|[-*+>]\s|\d+[.)]\s|\|)", lines[index - 1])
                  and (index == 1 or not lines[index - 2].strip())):
                level, title = (1 if stripped[0] == "=" else 2), lines[index - 1].strip()
            if level:
                title = re.sub(r"\s*\{[^{}]*\}\s*$", "", title)                      # {#id .unnumbered}
                title = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", title)             # links, images
                title = re.sub(r"[*`]|(?<!\w)_|_(?!\w)|\\(?=\W)", "", title).strip()
                if title:
                    found.append((level, title))
    return found


def search_form(text: str) -> str:
    """Text as compared when finding a heading on a page: ligatures and case undone, punctuation gone."""
    return " ".join(re.sub(r"[\W_]+", " ", unicodedata.normalize("NFKC", text).casefold()).split())


def locate_headings(headings: list[tuple[int, str]], page_texts: list[str]) -> list[tuple[int, int, str]]:
    """(page index, level, text) for the headings found in the PDF's own text, in document order. Each
    heading is looked for from the page of the previous one onward; a page that lists most of the
    headings (a table of contents) is only used when a heading is nowhere else."""
    pages = [search_form(text) for text in page_texts]
    forms = [search_form(title) for _, title in headings]
    contents = set()
    if len(headings) >= 4:
        for number, page in enumerate(pages):
            if sum(1 for form in forms if form and form in page) >= max(4, int(0.6 * len(headings))):
                contents.add(number)
    located, start = [], 0
    for (level, title), form in zip(headings, forms):
        if not form:
            continue
        for allowed in (False, True):
            hit = next((number for number in range(start, len(pages))
                        if form in pages[number] and (allowed or number not in contents)), None)
            if hit is not None:
                located.append((hit, level, title))
                start = hit
                break
    return located


def outline_entries(reader: "pypdf.PdfReader") -> list[tuple[int, int, str]]:
    """(page index, depth, title) of the PDF's existing bookmarks, flattened."""
    entries: list[tuple[int, int, str]] = []

    def walk(items, depth: int) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            try:
                entries.append((reader.get_destination_page_number(item), depth + 1, str(item.title)))
            except Exception:  # noqa: BLE001 -- a bookmark pointing nowhere
                continue

    walk(reader.outline, 0)
    return entries


def hf_text(value: str) -> str:
    """``value`` as far as Helvetica (WinAnsi) can draw it: accents are dropped, other letters become ``?``."""
    from pdfmd_inkmd.fonts import to_winansi_byte
    out = []
    for char in value:
        if to_winansi_byte(ord(char)) != ord("?") or char == "?":
            out.append(char)
            continue
        base = "".join(part for part in unicodedata.normalize("NFKD", char) if not unicodedata.combining(part))
        out.append(base if base and all(to_winansi_byte(ord(part)) != ord("?") for part in base) else "?")
    return "".join(out)


def hf_overlay(page: "pypdf.PageObject", values: dict[str, str],
               top: str | None, bottom: str | None) -> "pypdf.PageObject":
    """A transparent page carrying the header and footer text for one page."""
    from pdfmd_inkmd.fonts import text_width, to_winansi_byte
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    box = page.cropbox
    width, height = float(box.width), float(box.height)
    left, bottom_edge = float(box.left), float(box.bottom)
    overlay = core.pypdf.PageObject.create_blank_page(None, left + width, bottom_edge + height)
    commands = ["0.25 g"]
    for row, template in (("top", top), ("bottom", bottom)):
        if not template:
            continue
        y = bottom_edge + (height - 24.0 if row == "top" else 20.0)
        for slot, field in zip(("left", "middle", "right"), parse_hf_template(template)):
            text = hf_text(fill_hf_field(field, values))
            if not text:
                continue
            size = text_width(text, HF_FONT, HF_SIZE)
            x = {"left": left + HF_MARGIN, "middle": left + (width - size) / 2,
                 "right": left + width - HF_MARGIN - size}[slot]
            encoded = bytes(to_winansi_byte(ord(char)) for char in text if ord(char) != 0xAD)
            literal = encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            commands.append(f"BT /PdfmdHF {HF_SIZE:g} Tf {x:.2f} {y:.2f} Td ({literal.decode('latin-1')}) Tj ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("latin-1"))
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica"),
                             NameObject("/Encoding"): NameObject("/WinAnsiEncoding")})
    overlay[NameObject("/Contents")] = stream
    overlay[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/PdfmdHF"): font})})
    return overlay


def local_file_of_link(annotation, folder: Path) -> Path | None:
    """The existing local file a link annotation points at, or None (web links, anchors, missing files)."""
    action = annotation.get("/A")
    action = action.get_object() if action is not None else None
    if not action:
        return None
    target = action.get("/URI") if action.get("/S") == "/URI" else action.get("/F")
    if isinstance(target, dict):                       # a file specification
        target = target.get("/UF") or target.get("/F")
    if not isinstance(target, str) or not target.strip() or target.startswith("#"):
        return None
    target = urllib.parse.unquote(target.split("#", 1)[0].split("?", 1)[0])
    if re.match(r"[A-Za-z][A-Za-z0-9+.\-]+:", target) and not re.match(r"[A-Za-z]:[\\/]", target):
        if not target.lower().startswith("file:"):
            return None
        target = urllib.parse.urlparse(target).path
    path = Path(target)
    path = path if path.is_absolute() else folder / path
    try:
        return path.resolve() if path.is_file() else None
    except OSError:
        return None


def polish_wanted() -> bool:
    options = core.POLISH_CLI
    return bool(options.get("header") or options.get("footer") or options.get("bookmarks")
                or options.get("attach_links") or options.get("info"))


@_timed("polish PDF")
def polish_pdf(pdf_path: Path, sources: list[Path], verbose: bool = False) -> None:
    """Apply the requested finishing touches to the built ``pdf_path``; a failure leaves the PDF as it was."""
    options = core.POLISH_CLI
    if not polish_wanted() or core.pypdf is None or not pdf_path.is_file():
        return
    from pypdf.generic import (ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject,
                               TextStringObject)
    pypdf_logger = logging.getLogger("pypdf")
    previous_level = pypdf_logger.level
    pypdf_logger.setLevel(logging.ERROR)
    done: list[str] = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reader = core.pypdf.PdfReader(pdf_path)
            writer = core.pypdf.PdfWriter(clone_from=reader)
            count = len(writer.pages)
            header_template, footer_template = options.get("header"), options.get("footer")
            for template in (header_template, footer_template):
                if template:
                    parse_hf_template(template)
            existing = outline_entries(reader)
            wants_headings = bool(options.get("bookmarks") and not existing) or any(
                template and re.search(r"\{(header|heading)\}", template) for template in (header_template, footer_template))
            titles: list[tuple[int, int, str]] = existing
            if wants_headings and not existing:
                texts = []
                for source in sources:
                    try:
                        texts.append(source.read_text(encoding="utf-8-sig"))
                    except (OSError, UnicodeDecodeError):
                        continue
                page_texts = [(page.extract_text() or "") for page in reader.pages]
                titles = locate_headings(markdown_headings(texts), page_texts)
                if options.get("bookmarks") and titles:
                    stack: list[tuple[int, object]] = []
                    for number, level, title in titles:
                        while stack and stack[-1][0] >= level:
                            stack.pop()
                        item = writer.add_outline_item(title, number, parent=stack[-1][1] if stack else None)
                        stack.append((level, item))
                    writer.page_mode = "/UseOutlines"
                    done.append(f"{len(titles)} bookmarks")
            elif options.get("bookmarks") and existing:
                done.append(f"{len(existing)} bookmarks already there")
            if header_template or footer_template:
                top_level = min((level for _, level, _ in titles), default=1)
                today = datetime.now().date().isoformat()
                document_title = str((reader.metadata or {}).get("/Title") or options.get("info", {}).get("/Title") or "")
                skipped_rotation = False
                for number, page in enumerate(writer.pages):
                    if page.get("/Rotate", 0) not in (0, None):
                        skipped_rotation = True
                        continue
                    current = [title for index, level, title in titles if index <= number and level == top_level]
                    values = {"page": str(number + 1), "pages": str(count), "date": today,
                              "header": current[-1] if current else "", "heading": current[-1] if current else "",
                              "title": document_title}
                    page.merge_page(hf_overlay(page, values, header_template, footer_template))
                if skipped_rotation:
                    print("WARN  header/footer: rotated pages were left without them", file=sys.stderr)
                done.append("header/footer")
            if options.get("attach_links"):
                folder = sources[0].resolve().parent if sources else pdf_path.resolve().parent
                added: dict[Path, object] = {}
                names: set[str] = set()
                for page in writer.pages:
                    kept = ArrayObject()
                    for reference in page.get("/Annots") or []:
                        annotation = reference.get_object()
                        target = local_file_of_link(annotation, folder) if annotation.get("/Subtype") == "/Link" else None
                        if target is None or target == pdf_path.resolve():
                            kept.append(reference)
                            continue
                        if target.stat().st_size > LINKED_FILE_LIMIT:
                            print(f"WARN  not attached (over 25 MB): {core.display_path(target)}", file=sys.stderr)
                            kept.append(reference)
                            continue
                        if target not in added:
                            try:
                                name = "linked/" + target.relative_to(folder).as_posix()
                            except ValueError:
                                name = "linked/" + target.name
                            while name in names:
                                name += "_"
                            names.add(name)
                            embedded = core.add_deflated_attachment(writer, name, target.read_bytes())
                            filespec = writer._add_object(DictionaryObject({
                                NameObject("/Type"): NameObject("/Filespec"), NameObject("/F"): TextStringObject(name),
                                NameObject("/UF"): TextStringObject(name),
                                NameObject("/EF"): DictionaryObject({NameObject("/F"): embedded.indirect_reference})}))
                            added[target] = (filespec, name)
                        filespec, name = added[target]
                        x0, y0, x1, y1 = (float(value) for value in annotation["/Rect"])
                        clip_x = float(page.cropbox.right) - 24.0     # in the margin, level with the link
                        kept.append(writer._add_object(DictionaryObject({
                            NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/FileAttachment"),
                            NameObject("/Rect"): ArrayObject([FloatObject(clip_x), FloatObject(max(y0, y1) - 12),
                                                              FloatObject(clip_x + 12), FloatObject(max(y0, y1))]),
                            NameObject("/FS"): filespec, NameObject("/Name"): NameObject("/Paperclip"),
                            NameObject("/Contents"): TextStringObject(name), NameObject("/F"): NumberObject(4)})))
                    if len(kept) != len(page.get("/Annots") or []) or kept:
                        page[NameObject("/Annots")] = kept
                if added:
                    done.append(f"{len(added)} linked file" + ("s" if len(added) != 1 else "") + " attached")
            if options.get("info"):
                writer.add_metadata(dict(options["info"]))
                done.append("properties")
            core.atomic_write_pdf(writer, pdf_path)
        if done:
            print(f"PDF   {core.display_path(pdf_path)}: " + ", ".join(done))
    except ValueError as error:
        print(f"ERROR {error}", file=sys.stderr)
    except Exception as error:  # noqa: BLE001 -- the PDF itself is already fine
        print(f"WARN  could not finish the PDF ({type(error).__name__}: {error}); it is left as built",
              file=sys.stderr)
    finally:
        pypdf_logger.setLevel(previous_level)
