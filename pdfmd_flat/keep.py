"""`--keep-source`: a Markdown output that carries its own source as a trailing HTML comment (v3.26.4).

The flat Markdown of `--to gfm` cannot be turned back into the document it came from (ids, numbers, citations, scripts and
translated raw pieces are gone). So the file may end with one comment that holds the document's whole source, the very
set of files `--attach-source` puts into a PDF (the merged Markdown, a manifest of the layout, the data files), and
`pdfmd --restore FILE.md` writes them back.

The comment must survive whatever the source contains: `-->`, `--!>`, `<!-- nested -->`, the marker itself, CRLF. Two
encodings, both safe by construction:

* ``packed`` (default): the entries as one JSON, zlib-compressed, base64 in lines of 76. Base64 has no `-`, `<` or `>`,
  so nothing in the payload can close or open a comment.
* ``readable``: each entry as text, with ``\\`` ``>`` CR and a line-initial ``=`` or ``<`` escaped by a backslash. No bare
  ``>`` survives, so no ``-->`` or ``--!>`` can appear; no line begins with ``<`` or ``=``, so the marker and the section lines
  cannot be imitated. Reversible character for character.

A hash of the body (everything before the comment) is stored so a restore can say the body was edited since.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import zlib

MARKER = "<!-- pdfmd-source"
FORMAT = 1
MODES = ("packed", "readable")
WARN_BYTES = 1024 * 1024
SECTION = "== "


class KeepError(ValueError):
    pass


def digest(body: str) -> str:
    """The hash of a body: its text without trailing newlines (the comment is appended after one blank line)."""
    return hashlib.sha256(body.rstrip("\n").encode("utf-8")).hexdigest()


def escape(text: str) -> str:
    """`text` with no `>` in it, no CR, and no line starting with `<` or `=`; `unescape` is its exact inverse."""
    out = text.replace("\\", "\\\\").replace(">", "\\>").replace("\r", "\\r")
    return re.sub(r"(?m)^([<=])", r"\\\1", out)


def unescape(text: str) -> str:
    return re.sub(r"\\(.)", lambda match: "\r" if match.group(1) == "r" else match.group(1), text, flags=re.DOTALL)


def _wrap(data: str, width: int = 76) -> str:
    return "\n".join(data[index:index + width] for index in range(0, len(data), width))


def pack(entries: dict[str, bytes], body: str, mode: str = "packed", source: str = "", pdfmd: str = "") -> str:
    """The trailing comment (ending with a newline) that carries `entries` for a Markdown file whose body is `body`."""
    if mode not in MODES:
        raise KeepError(f"keep-source mode {mode!r}: choose one of {', '.join(MODES)}")
    header = [f"{MARKER} {FORMAT}", f"encoding: {mode}", f"body-sha256: {digest(body)}"]
    if source:
        header.append("source: " + source.replace("\n", " ").replace(">", ""))
    if pdfmd:
        header.append(f"pdfmd: {pdfmd}")
    if mode == "packed":
        document = json.dumps({name: base64.b64encode(data).decode("ascii") for name, data in entries.items()},
                              sort_keys=True)
        payload = _wrap(base64.b64encode(zlib.compress(document.encode("utf-8"), 9)).decode("ascii"))
        return "\n".join(header) + "\n\n" + payload + "\n-->\n"
    sections = []
    for name, data in entries.items():
        try:
            text, kind = data.decode("utf-8"), "text"
        except UnicodeDecodeError:
            text, kind = _wrap(base64.b64encode(data).decode("ascii")), "base64"
        sections.append(f"{SECTION}{name}" + (f" ({kind})" if kind != "text" else "") + "\n" + escape(text))
    return "\n".join(header) + "\n\n" + "\n".join(sections) + "\n-->\n"


class Trailer:
    def __init__(self, start: int, header: dict[str, str], payload: str):
        self.start = start
        self.header = header
        self.payload = payload

    @property
    def mode(self) -> str:
        return self.header.get("encoding", "")

    @property
    def body_hash(self) -> str:
        return self.header.get("body-sha256", "")


def find(text: str) -> Trailer | None:
    """The trailer at the end of `text`, or None. The LAST marker at the start of a line that is followed by a proper
    end of file: a body that talks about the marker (a code block, say) does not confuse it."""
    if not text.rstrip().endswith("-->"):
        return None
    index = text.rfind("\n" + MARKER + " ")
    if index < 0:
        if not text.startswith(MARKER + " "):
            return None
        index = -1
    start = index + 1
    block = text[start:]
    head, separator, rest = block.partition("\n\n")
    if not separator:
        return None
    lines = head.split("\n")
    first = lines[0][len(MARKER):].strip()
    if not first.isdigit():
        return None
    if int(first) > FORMAT:
        raise KeepError(f"the source in this file was written by a newer pdfmd (format {first}); upgrade pdfmd")
    header = {}
    for line in lines[1:]:
        key, _, value = line.partition(":")
        header[key.strip()] = value.strip()
    rest = rest.rstrip()
    if not rest.endswith("-->"):
        return None
    payload = rest[:-3]
    if payload.endswith("\n"):
        payload = payload[:-1]          # the one newline pack() wrote before the closing "-->"
    return Trailer(start, header, payload)


def unpack(trailer: Trailer) -> dict[str, bytes]:
    """The entries a trailer carries."""
    if trailer.mode == "packed":
        try:
            document = json.loads(zlib.decompress(base64.b64decode("".join(trailer.payload.split()))).decode("utf-8"))
            return {name: base64.b64decode(data) for name, data in document.items()}
        except (ValueError, zlib.error) as error:
            raise KeepError(f"the packed source in this file is damaged ({error})")
    if trailer.mode == "readable":
        entries: dict[str, bytes] = {}
        name = kind = None
        buffer: list[str] = []

        def close() -> None:
            if name is None:
                return
            text = "\n".join(buffer)
            entries[name] = (base64.b64decode("".join(text.split())) if kind == "base64"
                             else unescape(text).encode("utf-8"))

        for line in trailer.payload.split("\n"):
            if line.startswith(SECTION):
                close()
                label = line[len(SECTION):]
                kind = "text"
                if label.endswith(" (base64)"):
                    label, kind = label[:-len(" (base64)")], "base64"
                name, buffer = label, []
            else:
                buffer.append(line)
        close()
        return entries
    raise KeepError(f"the source in this file uses an encoding this pdfmd does not know ({trailer.mode or 'none'})")


def split(text: str) -> tuple[str, Trailer | None]:
    """(the body, the trailer) of a Markdown file's text."""
    trailer = find(text)
    if trailer is None:
        return text, None
    return text[:trailer.start], trailer


def append(body: str, trailer: str) -> str:
    """The file's text: the body, one blank line, the trailer."""
    return body.rstrip("\n") + "\n\n" + trailer
