"""Plain hide/hidden containers: read first, remove at the end; source copies stay literal."""
from __future__ import annotations

import re

from pdfmd_base import core


DIV = re.compile(r"(?m)^[ \t]*(?:(?:>[ \t]*)+)?(:{3,})[ \t]*(.*?)[ \t]*$")
CLASSES = re.compile(r"(?<!\S)\.(hide|hidden|calc)(?![\w-])")


def show_hidden(source, metadata_files=()):
    value = core.SHOW_HIDDEN_CLI
    if value is None:
        value = core.first_pdfmd_option(source, list(metadata_files), "show-hidden")
    return core.option_flag(value) is True


def ranges(text):
    """Source intervals of plain hidden divs/spans, excluding code and front matter.

    Keep source offsets (and hence the spelling of everything outside a removed
    container). Balance nested divs and brackets; do not parse a code example.
    """
    from pdfmd_check.lint import mask_code

    _, body = core.split_front_matter(text)
    offset = len(text) - len(body)
    masked, _ = mask_code(body)
    found, stack = [], []
    for match in DIV.finditer(masked):
        attrs = match[2].strip()
        if not attrs:
            if stack:
                start, hidden = stack.pop()
                if hidden:
                    end = match.end() + (masked[match.end():match.end() + 1] == "\n")
                    found.append((offset + start, offset + end))
            continue
        classes = set(CLASSES.findall(attrs.strip("{} ")))
        plain = attrs in ("hide", "hidden") or bool(classes & {"hide", "hidden"}) and "calc" not in classes
        stack.append((match.start(), plain))
    for start, hidden in stack:  # Pandoc closes an unclosed fenced div at EOF
        if hidden:
            found.append((offset + start, len(text)))
    found.extend((offset + start, offset + end) for start, close, end in spans(masked))
    merged = []
    for start, end in sorted(found):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def spans(masked):
    brackets = []
    for match in re.finditer(r"(?<!\\)[\[\]]", masked):
        if match[0] == "[":
            brackets.append(match.start())
        elif brackets:
            start = brackets.pop()
            attrs = re.match(r"\{([^{}]*)\}", masked[match.end():])
            if attrs and set(CLASSES.findall(attrs[1])) & {"hide", "hidden"}:
                yield start, match.start(), match.end() + attrs.end()


def reveal_hidden(text):
    """The native reader has no span attributes: reveal their ordinary contents."""
    from pdfmd_check.lint import mask_code

    _, body = core.split_front_matter(text)
    offset = len(text) - len(body)
    masked, _ = mask_code(body)
    edits = []
    for start, close, end in spans(masked):
        edits.extend(((offset + start, offset + start + 1), (offset + close, offset + end)))
    for start, end in sorted(edits, reverse=True):
        text = text[:start] + text[end:]
    return text


def strip_hidden(text):
    for start, end in reversed(ranges(text)):
        text = text[:start] + text[end:]
    return text


def native_text(text, source, metadata_files=()):
    # The native tier has no calculator (as before); hiding needs no Pandoc.
    return reveal_hidden(text) if show_hidden(source, metadata_files) else strip_hidden(text)


def mark_args(inputs, metadata_files):
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []

    files = inputs if isinstance(inputs, list) else [inputs]
    shown = show_hidden(files[0], metadata_files)
    path = pdfmd_lua.path("hidden_mark")
    return ["-M", "pdfmd-show-hidden=" + str(shown).lower(), "--lua-filter", str(path)] if path else []


def finish_args():
    try:
        import pdfmd_lua
    except ImportError:
        return []

    path = pdfmd_lua.path("hidden")
    return ["--lua-filter", str(path)] if path else []
