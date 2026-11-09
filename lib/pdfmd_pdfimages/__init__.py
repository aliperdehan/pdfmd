"""The pictures of a built PDF: the PNG and size helpers, the search for which picture of a PDF a source image is, the
extraction of the pictures a plain attach did not store (a JPEG as its own bytes, a raster as a PNG of its pixels, an SVG or PDF
figure as a one-page PDF), and the rewriting of the image paths in Markdown and LaTeX when a restored picture got a new name.

Moved out of `pdfmd.py` unchanged (v3.33.14, SPLIT.md), with `DECODE_LIMIT` and `SVG_UNITS`. `core` is the `pdfmd` module, bound by
`pdfmd.py` when it loads (the first binding wins); the pdfmd names the code uses (`GRAPHIC_RE`, `IMAGE_REF_RE`) are read as
`core.X` when it runs, and so is `core.pypdf`, a lazy loader there, so pypdf is never imported at the top here (the
`from pypdf.generic import ...` lines stay inside the functions, as they were).
"""

from __future__ import annotations

import hashlib
import io
import posixpath
import re
import struct
import urllib.parse
import zlib
from pathlib import Path, PurePosixPath

core = None


SVG_UNITS = {"": 0.75, "px": 0.75, "pt": 1.0, "pc": 12.0, "mm": 72 / 25.4, "cm": 72 / 2.54, "in": 72.0}
DECODE_LIMIT = 64 * 1024 * 1024


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_png(width: int, height: int, depth: int, colour: int, rows: bytes,
               palette: bytes | None = None) -> bytes:
    """A PNG of ``rows`` (the samples of every scanline, each padded to a byte, no filter byte)."""
    stride = len(rows) // height
    raw = b"".join(b"\x00" + rows[line * stride:(line + 1) * stride] for line in range(height))
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, 0))
            + (png_chunk(b"PLTE", palette) if palette else b"") + png_chunk(b"IDAT", zlib.compress(raw, 9))
            + png_chunk(b"IEND", b""))


def file_picture_size(path: Path) -> tuple[str, float, float] | None:
    """('raster', width, height) in pixels for a PNG, JPEG or GIF; ('vector', width, height)
    in points for an SVG or a PDF; None for anything else or anything unreadable."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".png":
            with path.open("rb") as handle:
                head = handle.read(24)
            return ("raster", *struct.unpack(">II", head[16:24])) if head[:8] == b"\x89PNG\r\n\x1a\n" else None
        if suffix in (".jpg", ".jpeg"):
            data = path.read_bytes()
            position = 2
            while position + 9 < len(data):
                if data[position] != 0xFF:
                    position += 1
                    continue
                marker = data[position + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                    position += 1 if marker == 0xFF else 2
                    continue
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    height, width = struct.unpack(">HH", data[position + 5:position + 9])
                    return "raster", width, height
                position += 2 + struct.unpack(">H", data[position + 2:position + 4])[0]
            return None
        if suffix == ".gif":
            with path.open("rb") as handle:
                width, height = struct.unpack("<HH", handle.read(10)[6:10])
            return "raster", width, height
        if suffix == ".svg":
            root = re.search(r"<svg\b[^>]*>", path.read_text(encoding="utf-8", errors="replace"), re.DOTALL)
            if root is None:
                return None
            dimension: dict[str, float] = {}
            for name in ("width", "height"):
                found = re.search(r"\b" + name + r"\s*=\s*[\"']\s*([0-9.]+)\s*([a-z%]*)\s*[\"']", root.group(0))
                if found and found.group(2) in SVG_UNITS:
                    dimension[name] = float(found.group(1)) * SVG_UNITS[found.group(2)]
            if len(dimension) < 2:
                box = re.search(r"viewBox\s*=\s*[\"']\s*[-0-9.]+[ ,]+[-0-9.]+[ ,]+([0-9.]+)[ ,]+([0-9.]+)", root.group(0))
                if box is None:
                    return None
                dimension = {"width": float(box.group(1)) * 0.75, "height": float(box.group(2)) * 0.75}
            return "vector", dimension["width"], dimension["height"]
        if suffix == ".pdf" and core.pypdf is not None:
            box = core.pypdf.PdfReader(path).pages[0].cropbox
            return "vector", float(box.width), float(box.height)
    except Exception:  # noqa: BLE001 -- a hint, never a failure
        return None
    return None


def pdf_pictures(reader) -> list[dict]:
    """The images and forms drawn on the pages of ``reader`` (top level), in page order:
    {id, kind 'image'|'form', stream sha256, width, height, object}. An image that is
    some other image's soft mask is left out."""
    masks: set[int] = set()
    found: list[dict] = []
    seen: set[int] = set()
    for page in reader.pages:
        resources = page.get("/Resources")
        resources = resources.get_object() if resources is not None else {}
        xobjects = resources.get("/XObject")
        if xobjects is None:
            continue
        for _, reference in xobjects.get_object().items():
            if reference.idnum in seen:
                continue
            seen.add(reference.idnum)
            obj = reference.get_object()
            subtype = obj.get("/Subtype")
            try:
                raw = obj._data if hasattr(obj, "_data") else b""
                if subtype == "/Image":
                    mask = obj.get("/SMask")
                    if mask is not None and hasattr(mask, "idnum"):
                        masks.add(mask.idnum)
                    found.append({"id": reference.idnum, "kind": "image", "sha256": hashlib.sha256(raw).hexdigest(),
                                  "width": int(obj["/Width"]), "height": int(obj["/Height"]), "object": obj})
                elif subtype == "/Form":
                    box = [float(item) for item in obj["/BBox"]]
                    found.append({"id": reference.idnum, "kind": "form", "sha256": hashlib.sha256(raw).hexdigest(),
                                  "width": abs(box[2] - box[0]), "height": abs(box[3] - box[1]), "object": obj})
            except (KeyError, TypeError, ValueError):
                continue
    return [item for item in found if item["id"] not in masks]


def match_images_to_pdf(pdf_path: Path, images: list[dict], base: Path) -> None:
    """Add a ``pdf`` record to each of ``images`` ({path, ...}) that can be found in the PDF."""
    if not images or core.pypdf is None:
        return
    pictures = pdf_pictures(core.pypdf.PdfReader(pdf_path))
    taken: set[int] = set()
    for image in images:
        path = base / image["path"]
        size = file_picture_size(path)
        if size is None:
            continue
        kind, width, height = size
        match = None
        if kind == "raster":
            if path.suffix.lower() in (".jpg", ".jpeg"):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                match = next((item for item in pictures if item["kind"] == "image" and item["sha256"] == digest
                              and item["id"] not in taken), None)
            if match is None:
                match = next((item for item in pictures if item["kind"] == "image" and item["id"] not in taken
                              and (item["width"], item["height"]) == (int(width), int(height))), None)
        else:
            match = next((item for item in pictures if item["kind"] == "form" and item["id"] not in taken
                          and abs(item["width"] - width) < 0.6 and abs(item["height"] - height) < 0.6), None)
        if match is not None:
            taken.add(match["id"])
            image["pdf"] = {"kind": match["kind"], "sha256": match["sha256"],
                            "width": round(match["width"], 3), "height": round(match["height"], 3)}


def samples_to_png(obj) -> bytes | None:
    """A PNG of an image XObject's pixels, or None if it is a kind this cannot write."""
    if obj.get("/Decode") is not None or obj.get("/Mask") is not None or obj.get("/ImageMask"):
        return None
    width, height = int(obj["/Width"]), int(obj["/Height"])
    depth = int(obj.get("/BitsPerComponent", 8))
    space = obj.get("/ColorSpace")
    space = space.get_object() if space is not None else None
    palette = None
    if isinstance(space, list) and space and str(space[0]) == "/Indexed":
        lookup = space[3].get_object()
        palette = lookup.get_data() if hasattr(lookup, "get_data") else bytes(lookup)
        palette = palette[:3 * (int(space[2]) + 1)]
        colour, channels = 3, 1
    else:
        name = str(space[0] if isinstance(space, list) and space else space)
        if name == "/ICCBased":
            channels = int(space[1].get_object().get("/N", 3))
            name = {1: "/DeviceGray", 3: "/DeviceRGB"}.get(channels, "")
        if name in ("/DeviceGray", "/CalGray"):
            colour, channels = 0, 1
        elif name in ("/DeviceRGB", "/CalRGB"):
            colour, channels = 2, 3
        else:
            return None
    stride = (width * channels * depth + 7) // 8
    if obj.get("/SMask") is None:
        # A PNG that LuaTeX or pdfTeX included is in the PDF as its own IDAT data (Flate with a PNG predictor): the same
        # bytes make the PNG again. Decoding it here lost 1-bit pictures (pypdf unfilters them with a pixel of 0 bytes), and
        # recompressing the rows is slower for nothing (v3.28.38).
        params = obj.get("/DecodeParms")
        params = params.get_object() if hasattr(params, "get_object") else params
        if isinstance(params, list) and len(params) == 1:
            params = params[0].get_object() if hasattr(params[0], "get_object") else params[0]
        flate = obj.get("/Filter")
        flate = flate[0] if isinstance(flate, list) and len(flate) == 1 else flate
        if (str(flate) == "/FlateDecode" and hasattr(params, "get") and int(params.get("/Predictor", 1)) >= 10
                and int(params.get("/Colors", 1)) == channels and int(params.get("/BitsPerComponent", 8)) == depth
                and int(params.get("/Columns", 1)) == width and getattr(obj, "_data", None)):
            return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, 0))
                    + (png_chunk(b"PLTE", palette) if palette else b"") + png_chunk(b"IDAT", bytes(obj._data))
                    + png_chunk(b"IEND", b""))
    rows = obj.get_data()
    if len(rows) < stride * height or width * height * channels * max(depth, 8) // 8 > DECODE_LIMIT:
        return None
    rows = rows[:stride * height]
    mask = obj.get("/SMask")
    if mask is not None and depth == 8 and colour in (0, 2):
        mask = mask.get_object()
        alpha = mask.get_data()
        if (int(mask["/Width"]), int(mask["/Height"]), int(mask.get("/BitsPerComponent", 8))) == (width, height, 8) \
                and len(alpha) >= width * height:
            pixels = bytearray()
            for index in range(width * height):
                row, column = divmod(index, width)
                start = row * stride + column * channels
                pixels += rows[start:start + channels] + alpha[index:index + 1]
            return encode_png(width, height, 8, colour + 4, bytes(pixels))
    return encode_png(width, height, depth, colour, rows, palette)


def form_to_pdf(reader, picture: dict) -> bytes:
    """A one-page PDF drawing the form ``picture`` (an SVG or PDF figure as the PDF holds it)."""
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    form = picture["object"]
    box = [float(item) for item in form["/BBox"]]
    writer = core.pypdf.PdfWriter()
    page = writer.add_blank_page(width=abs(box[2] - box[0]), height=abs(box[3] - box[1]))
    cloned = writer._add_object(form.clone(writer))
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/Fm0"): cloned})})
    drawing = DecodedStreamObject()
    drawing.set_data(f"q 1 0 0 1 {-min(box[0], box[2]):.4f} {-min(box[1], box[3]):.4f} cm /Fm0 Do Q".encode())
    page[NameObject("/Contents")] = writer._add_object(drawing)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def extract_pdf_images(pdf_path: Path, images: list[dict], skip: set[str]) -> tuple[dict[str, bytes], dict[str, str], list[str]]:
    """The pictures of ``images`` ({path, pdf: {...}}) taken out of the PDF: ({path: bytes},
    {path: the name it is restored under, where that is not its own}, paths that could not be)."""
    out: dict[str, bytes] = {}
    renamed: dict[str, str] = {}
    failed: list[str] = []
    wanted = [image for image in images if image.get("pdf") and image["path"] not in skip]
    if not wanted:
        return out, renamed, failed
    reader = core.pypdf.PdfReader(pdf_path)
    pictures = pdf_pictures(reader)
    for image in wanted:
        record = image["pdf"]
        same = [item for item in pictures if item["sha256"] == record["sha256"] and item["kind"] == record["kind"]]
        picture = next((item for item in same if (item["width"], item["height"]) == (record["width"], record["height"])),
                       same[0] if same else None)
        name = image["path"]
        try:
            if picture is None:
                raise ValueError("not in the PDF")
            if picture["kind"] == "form":
                data, target = form_to_pdf(reader, picture), str(PurePosixPath(name).with_suffix(".pdf"))
            elif str(picture["object"].get("/Filter")) == "/DCTDecode":
                data, target = picture["object"]._data, (name if PurePosixPath(name).suffix.lower() in (".jpg", ".jpeg")
                                                          else str(PurePosixPath(name).with_suffix(".jpg")))
            else:
                data = samples_to_png(picture["object"])
                if data is None:
                    raise ValueError("a kind of image this does not write")
                target = name if PurePosixPath(name).suffix.lower() == ".png" else str(PurePosixPath(name).with_suffix(".png"))
        except Exception:  # noqa: BLE001 -- one picture not coming out is not the restore failing
            failed.append(name)
            continue
        out[target] = data
        if target != name:
            renamed[name] = target
    return out, renamed, failed


def rewrite_tex_image_paths(text: str, renamed: dict[str, str], folder: str = "") -> str:
    """``text`` (LaTeX) with the \\includegraphics paths in ``renamed`` pointing at their new names. A path in a
    stored .tex is read as the file wrote it (``folder``: where that file sits, relative to the document) and
    as the document's own, with or without the extension."""
    if not renamed:
        return text

    def swap(match: "re.Match[str]") -> str:
        target = match.group(1).strip()
        for base in ((folder + "/") if folder else "", ""):
            joined = posixpath.normpath(base + target)
            for key, new in renamed.items():
                if joined in (key, str(PurePosixPath(key).with_suffix(""))):
                    kept = new if base == "" else posixpath.relpath(new, folder or ".")
                    if joined == key or PurePosixPath(target).suffix:
                        return match.group(0).replace(target, kept, 1)
                    return match.group(0).replace(target, str(PurePosixPath(kept).with_suffix("")), 1)
        return match.group(0)

    return core.GRAPHIC_RE.sub(swap, text)


def rewrite_image_paths(text: str, renamed: dict[str, str]) -> str:
    """``text`` (Markdown) with the image paths in ``renamed`` pointing at their new names."""
    if not renamed:
        return text

    def swap(match: "re.Match[str]") -> str:
        group = 1 if match.group(1) else 2
        target = match.group(group)
        new = renamed.get(urllib.parse.unquote(target.split("#")[0].split("?")[0]))
        if new is None:
            return match.group(0)
        start = match.start(group) - match.start()
        return match.group(0)[:start] + urllib.parse.quote(new, safe="/") + match.group(0)[start + len(target):]

    return core.IMAGE_REF_RE.sub(swap, text)
