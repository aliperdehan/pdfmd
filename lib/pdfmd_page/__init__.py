"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_page`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import re
from pathlib import Path

from pdfmd_base import core


LATEX_GEOMETRY_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\bgeometry\b[^}]*\}|\\geometry\s*\{")


def has_latex_geometry(text: str) -> bool:
    """Detect a raw ``\\usepackage{geometry}``/``\\geometry{...}`` call.

    This is a plain text search across the whole document, not just an
    extracted header-includes block -- a bare word "geometry" in prose can
    never accidentally match either LaTeX-command pattern, so scanning the
    raw file is safe and doesn't need to isolate the YAML value first.
    """
    return bool(LATEX_GEOMETRY_RE.search(text))


def has_geometry(md_path: Path, variables: list[str], metadata_files: list[Path] = (),
                 preamble_files: list[Path] = ()) -> bool:
    """Return whether a page-margin setting already exists somewhere Pandoc
    would see it: a -V variable (``geometry=...``, the nested
    ``geometry:...`` form, or a bare ``margin=...``), the document's own
    front matter (``geometry:``/``margin:``, scalar or a YAML block list
    like a ``top:``/``bottom:``/``left:``/``right:`` breakdown -- either
    form starts with a ``geometry:`` line, which is all the check looks
    for), a linked --metadata-file that sets either, or a raw LaTeX
    ``\\usepackage{geometry}``/``\\geometry{...}`` call already present in
    the document's own header-includes or an auto-included preamble.

    That last check matters because DEFAULT_MARGIN is injected as a Pandoc
    ``-V geometry:...`` variable, which becomes another
    ``\\usepackage[...]{geometry}`` call in the rendered LaTeX (Pandoc's own
    default template). Loading the same package twice with two different,
    non-empty option lists is a fatal "Option clash" error in LaTeX, so a
    preamble or header-includes that already loads ``geometry`` itself has
    to suppress our own injection rather than error out at compile time.
    Only LaTeX-family engines use the ``geometry`` package this backs; see
    DEFAULT_MARGIN.
    """
    if any(variable.startswith(("geometry=", "geometry:", "margin="))
           for variable in variables):
        return True
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = core.LEADING_FRONT_MATTER_RE.match(text)
    if front_matter and re.search(r"^(?:geometry|margin)\s*:", front_matter.group(1), re.MULTILINE):
        return True
    if any(re.search(r"(?m)^(?:geometry|margin)\s*:", metadata_file.read_text(encoding="utf-8-sig"))
           for metadata_file in metadata_files):
        return True
    if has_latex_geometry(text):
        return True
    return any(has_latex_geometry(preamble.read_text(encoding="utf-8-sig"))
               for preamble in preamble_files)


# Shared by frontmatter_margin_geometry_options() and fix_typst_margin()
# below to translate a margin setting written for ONE engine family into
# the variable the OTHER one actually reads -- geometry: (LaTeX) and
# margin: (Typst) each mean nothing at all to the other's template, so a
# document written/tested against one engine silently loses its margin
# the moment it's rendered through the other (has_geometry() already
# stops pdfmd's own DEFAULT_MARGIN from stepping on either, which is
# correct, but does nothing to make the document's OWN setting reach the
# engine that can't read it natively). Both directions normalize through
# one canonical shape: a {top, bottom, left, right} dict of raw dimension
# strings, physical sides only -- Typst's binding-aware `inside`/`outside`
# and `rest` have no LaTeX equivalent at all, so a `margin:` mapping using
# any of those three is left completely alone rather than guessed at.
MARGIN_SIDE_ALIASES = {
    "x": ("left", "right"),
    "y": ("top", "bottom"),
    "top": ("top",),
    "bottom": ("bottom",),
    "left": ("left",),
    "right": ("right",),
}


# geometry package option names -- includes the older t/b/l/r-margin
# spellings alongside the more common ones actually seen in practice.
GEOMETRY_SIDE_ALIASES = {
    "margin": ("top", "bottom", "left", "right"),
    "hmargin": ("left", "right"),
    "vmargin": ("top", "bottom"),
    "top": ("top",), "tmargin": ("top",),
    "bottom": ("bottom",), "bmargin": ("bottom",),
    "left": ("left",), "lmargin": ("left",),
    "right": ("right",), "rmargin": ("right",),
}


def parse_margin_sides(value) -> dict[str, str] | None:
    """Normalize a parsed (via PyYAML) Typst-shaped ``margin:`` value into
    a ``{top, bottom, left, right}`` dict of raw dimension strings -- or
    None when `value` is a scalar-shaped None/absent, or a mapping that
    uses ``inside``/``outside``/``rest`` (Typst's own binding-aware
    margins, with no LaTeX equivalent) or any other key this doesn't
    recognize, or isn't a scalar or mapping at all.

    A scalar (already the case fix_typst_margin() itself exists to
    correct on the Typst side) is uniform on all four sides.
    """
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        side_value = str(value)
        return {"top": side_value, "bottom": side_value, "left": side_value, "right": side_value}
    if not isinstance(value, dict):
        return None
    sides: dict[str, str] = {}
    for key, side_value in value.items():
        aliases = MARGIN_SIDE_ALIASES.get(str(key).strip().casefold())
        if not aliases:
            return None
        for side in aliases:
            sides[side] = str(side_value)
    return sides or None


def parse_geometry_sides(value) -> dict[str, str] | None:
    """Normalize a parsed (via PyYAML) ``geometry:`` value -- a bare
    "key=val" scalar, a comma-joined "key=val,key=val" scalar, or a YAML
    list of such strings, the three shapes Pandoc's own LaTeX template
    accepts -- into a ``{top, bottom, left, right}`` dict of raw dimension
    strings, or None when it contains anything this can't safely
    interpret: an option with no ``key=`` at all, or a key that isn't
    about a margin (``includehead``, ``showframe``, ...) -- the geometry
    package has many options that aren't page margins, and guessing wrong
    on those would be worse than leaving Typst's own defaults in place.
    """
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        items = value
    else:
        return None
    sides: dict[str, str] = {}
    for item in items:
        for part in item.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                return None
            key, _, side_value = part.partition("=")
            aliases = GEOMETRY_SIDE_ALIASES.get(key.strip().casefold())
            if not aliases:
                return None
            for side in aliases:
                sides[side] = side_value.strip()
    return sides or None


def sides_to_geometry_options(sides: dict[str, str]) -> list[str]:
    """Format a {top,bottom,left,right} dict as the geometry: option list
    Pandoc's LaTeX template expects -- collapsed to one ``margin=...``
    when all four sides given are equal, one option per side otherwise
    (only the sides actually present -- a mapping that only set ``x:``
    leaves top/bottom to LaTeX's own default, same as it would for Typst).
    """
    if len(sides) == 4 and len(set(sides.values())) == 1:
        return [f"margin={next(iter(sides.values()))}"]
    return [f"{side}={sides[side]}" for side in ("top", "bottom", "left", "right") if side in sides]


def frontmatter_margin_geometry_options(md_path: Path, variables: list[str],
                                        metadata_files: list[Path] = ()) -> list[str] | None:
    """Return the geometry: option list a document's own (or a linked
    --metadata-file's) ``margin:`` value translates to for LaTeX-family
    engines -- or None when there's nothing to translate.

    ``margin:`` is a real Pandoc variable for the TYPST template only (see
    fix_typst_margin() below) -- Pandoc's LaTeX template never reads it at
    all, only ``geometry:`` does. has_geometry() already treats a bare
    ``margin:`` (in the document's own front matter OR a metadata file --
    it checks both) as "a margin setting exists" (correctly, so
    DEFAULT_MARGIN isn't injected on top of it), but nothing translated
    that value into the one variable LaTeX's own template actually
    consumes -- so a document with ONLY ``margin: 2.54cm`` (or a
    ``top:``/``bottom:``/``left:``/``right:``/``x:``/``y:`` breakdown) and
    no ``geometry:`` silently kept LaTeX's own much wider article-class
    default margins on every LaTeX-family engine, the requested value
    never taking effect at all -- confirmed directly (2026-09-28) alongside
    the Typst-side bug the scalar case triggers (see fix_typst_margin()).

    Same precedence pdf-engine resolution uses (see
    frontmatter_pdfmd_options()'s callers): the document's own front
    matter is checked first; if it sets no ``margin:`` at all, each
    linked --metadata-file is checked next, in order, so a shared
    metadata.yaml can set ``margin:`` once for every document that finds
    it -- leaving it out entirely, the way this function's own first
    version did, meant a document with margin ONLY in a shared metadata
    file lost it silently on both engine families at once, worse than the
    bug this function exists to fix. A real ``geometry:`` anywhere -- the
    document's own front matter, any metadata file, or -V -- always wins,
    untouched, checked before any ``margin:`` in any source, same as
    has_geometry().

    Returns None when: no ``margin:`` in any source; a real ``geometry:``
    is set anywhere; YAML support is unavailable (falls back to the
    scalar-only regex this function used before parse_margin_sides()
    existed, since a real parse is needed for the mapping case -- checked
    per source, same order); or every ``margin:`` found uses Typst's
    ``inside``/``outside``/``rest`` keys, which have no LaTeX equivalent
    (see parse_margin_sides()).
    """
    if any(variable.startswith(("geometry=", "geometry:")) for variable in variables):
        return None
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = core.LEADING_FRONT_MATTER_RE.match(text)
    blocks = [front_matter.group(1)] if front_matter else []
    for metadata_file in core.metadata_files_by_priority(metadata_files):
        meta_text = metadata_file.read_text(encoding="utf-8-sig")
        # A --metadata-file may be fenced (---...---, same as front matter)
        # or completely bare -- Pandoc accepts either. yaml.safe_load()
        # chokes on the fenced shape as-is (a second "---" reads as a
        # second YAML document, "expected a single document in the
        # stream"), so unwrap it the same way md_path's own front matter
        # is, and only fall back to the raw text when it isn't fenced.
        meta_front_matter = core.LEADING_FRONT_MATTER_RE.match(meta_text)
        blocks.append(meta_front_matter.group(1) if meta_front_matter else meta_text)
    if any(re.search(r"^geometry\s*:", block, re.MULTILINE) for block in blocks):
        return None
    for block in blocks:
        if core.yaml is None:
            match = re.search(r"^margin\s*:[ \t]*(\S.*?)[ \t]*$", block, re.MULTILINE)
            if not match:
                continue
            value = match.group(1).strip().strip("'\"")
            return [f"margin={value}"] if value else None
        try:
            data = core.yaml.safe_load(block)
        except core.yaml.YAMLError:
            continue
        if not isinstance(data, dict) or "margin" not in data:
            continue
        sides = parse_margin_sides(data["margin"])
        return sides_to_geometry_options(sides) if sides else None
    return None


def pagesize_typo_value(md_path: Path, variables: list[str]) -> str | None:
    """Return a document's own ``pagesize:`` value, IF ``papersize:`` isn't
    already set anywhere Pandoc would see it -- a -V variable or the
    document's own front matter.

    ``pagesize`` is not a Pandoc variable at all (the real one is
    ``papersize:``) -- LaTeX's own \\documentclass options include a
    same-named ``a4paper``/``letterpaper`` *class* option, and it's an easy,
    silent mistake to write ``pagesize: a4`` expecting the same effect
    ``papersize: a4`` gets from Pandoc's own template. Pandoc's metadata
    system doesn't error on an unrecognized key -- it just sits there
    unused -- so a document can carry this typo indefinitely with no
    warning, quietly rendering at whatever the default paper size is (US
    Letter) instead of the one actually intended. Found directly (CHEM 341
    session, 2026-09-20): the task brief for that document already knew
    about this exact trap (`pagesize: a4` producing a Letter PDF) and had to
    document it as a known caveat rather than get it fixed -- worth pdfmd
    catching automatically instead. Only checked when ``papersize`` is
    absent so a document that deliberately sets both (maybe mid-migration)
    is left alone -- its own explicit ``papersize:`` always wins.
    """
    if any(variable.startswith("papersize") for variable in variables):
        return None
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    block = front_matter.group(1)
    if re.search(r"^papersize\s*:", block, re.MULTILINE):
        return None
    match = re.search(r"^pagesize\s*:\s*(.+?)\s*$", block, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip("'\"")
    return value or None


def frontmatter_papersize_value(md_path: Path) -> str | None:
    """Return a document's own ``papersize:`` value straight from its front
    matter (a real Pandoc variable, unlike ``pagesize:`` above) -- used only
    to feed typst_papersize_translation() below, not for the pagesize-typo
    detection this sits next to.
    """
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    match = re.search(r"^papersize\s*:\s*(.+?)\s*$", front_matter.group(1), re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip("'\"")
    return value or None


# Pandoc's own `papersize:` variable is LaTeX-shaped by convention ("letter",
# "legal", "a4", ...matching what a LaTeX \documentclass option expects), and
# Pandoc's LaTeX template maps it accordingly -- but Pandoc's TYPST template
# passes the same string straight through to typst's own `page(paper: ...)`
# set rule, which does NOT accept "letter"/"legal" at all; typst's own names
# are "us-letter"/"us-legal" (most other names, "a4"/"a3"/"a5"/..., already
# match typst's own naming and need no translation -- only these two are
# known to differ). A document with `papersize: letter` compiles fine on
# every LaTeX-family engine and then silently errors (or falls back to
# typst's own default) the moment --to typst is used instead -- raised
# directly (2026-09-20): "works with tex, but not with typst". Only these
# two confirmed aliases are included; extend TYPST_PAPERSIZE_ALIASES if
# another one is found to differ the same way.
TYPST_PAPERSIZE_ALIASES = {
    "letter": "us-letter",
    "legal": "us-legal",
}


def typst_papersize_translation(value: str | None) -> str | None:
    """Return typst's own name for a Pandoc papersize value, or None when
    `value` is falsy or already fine as-is (either it's not one of the
    known-different names, or it's already typst-shaped)."""
    if not value:
        return None
    return TYPST_PAPERSIZE_ALIASES.get(value.strip().casefold())


def paper_kind(engine: str | None, no_auto: list[str] | None) -> str | None:
    """The kind of paper handling (paper_variables) for an engine or output: LaTeX ones, Typst, WeasyPrint."""
    if core.auto_disabled(no_auto, "papersize"):
        return None
    return "tex" if engine in core.LATEX_ENGINES - {"context"} | {"tex"} else engine if engine in ("typst", "weasyprint") else None


PAPER_ORIENTATIONS = ("landscape", "portrait")


LATEX_CLASS_PAPERS = frozenset({"a4", "a5", "b5", "letter", "legal", "executive"})      # the paper options of a LaTeX class


TYPST_PAPER_NAMES = {"letter": "us-letter", "legal": "us-legal", "tabloid": "us-tabloid", "ledger": "us-ledger",
                     "executive": "us-executive", "folio": "us-foolscap-folio"}


def paper_words(value) -> tuple[str, str]:
    """`a4,landscape` -> (`a4`, `landscape`): the size and the orientation of a `papersize:` value, "" for each that is not
    there. The size is lower case, without a trailing `paper` (`a4paper`) and with `us-letter` as `letter`."""
    size, orientation = "", ""
    for word in re.split(r"[,\s]+", core.scalar_text(value)):
        name = word.casefold()
        if name in PAPER_ORIENTATIONS:
            orientation = name
        elif name:
            name = core.PAPER_NAME_ALIASES.get(name, name)
            size = size or (name[:-5] if name.endswith("paper") and len(name) > 5 else name)
    return size, orientation


def paper_variables(md_path: Path, metadata_files: list[Path], variables: list[str], pagesize_typo: str | None,
                    kind: str | None) -> tuple[list[str], str | None]:
    """(variables, pagesize_typo) with the paper of the document settled for one kind of output (v3.30.42): "tex" (a LaTeX
    engine), "typst" or "weasyprint"; any other kind is returned as it came. Pandoc's `papersize` is a LaTeX class option, so
    `a4,landscape` printed `[a4,landscapepaper]` (a Letter page, silently), `a4paper` printed `a4paperpaper`, `a3` is no
    class option, and Typst and WeasyPrint did not read it: pdfmd gives each engine its own spelling. The paper of
    `--paper`, `-V papersize=` or the front matter, its orientation word, and `landscape` in `geometry:` or
    `classoption:` all reach the page. A single `-V papersize=` is left alone when it is already right."""
    if kind not in ("tex", "typst", "weasyprint"):
        return variables, pagesize_typo
    given = [item.split("=", 1)[1] for item in variables if item.startswith("papersize=")]
    merged = core.effective_metadata(md_path, metadata_files, variables)
    raw = given[-1] if given else (pagesize_typo or core.scalar_text(merged.get("papersize")))
    size, orientation = paper_words(raw)
    module = core.office_module()
    landscape = orientation == "landscape"
    if not orientation and module is not None:
        landscape = module.spec_from_metadata(merged, None, "exact").landscape
    rest = [item for item in variables if not item.startswith("papersize=")]
    if kind == "tex":
        extra: list[str] = []
        paper = size
        if size not in LATEX_CLASS_PAPERS and re.fullmatch(r"[abc][0-6]", size):
            paper = ""                                       # `a3`: geometry has it, the class does not
            extra.append(f"geometry:{size}paper")
        if orientation == "landscape":
            extra.append("geometry:landscape")
        if len(given) <= 1 and paper == raw and not extra:
            return variables, pagesize_typo
        if not raw:
            return variables, pagesize_typo
        return rest + ([f"papersize={paper}"] if paper or not given else []) + extra, None
    if kind == "typst":
        if not raw and not landscape:
            return variables, pagesize_typo
        name = TYPST_PAPER_NAMES.get(size) or (f"iso-{size}" if re.fullmatch(r"[bc][0-8]", size) else size)
        return rest + ([f"papersize={name}"] if name else []) + (["pdfmd-page-flipped=true"] if landscape else []), None
    points = core.NATIVE_PAPER_POINTS.get(size)
    if points is None and not landscape:
        return variables, pagesize_typo
    if points is None:
        css = "landscape"
    else:
        width, height = (points[1], points[0]) if landscape else points
        css = f"{width:g}pt {height:g}pt"
    return rest + [f"pdfmd-page={css}"], pagesize_typo


TYPST_MARGIN_RE = re.compile(r"^(?P<indent>[ \t]*)margin(?P<colon>[ \t]*:[ \t]*)(?P<val>\S.*?)[ \t]*$",
                             re.MULTILINE)


def sides_to_typst_margin_yaml(sides: dict[str, str], indent: str, newline: str) -> str:
    """Format a {top,bottom,left,right} dict as the YAML ``margin:``
    mapping Pandoc's Typst template needs -- collapsed to ``x:``/``y:``
    when all four sides given are equal, one line per side otherwise
    (only the sides actually present, in a fixed top/bottom/left/right
    order for a stable, readable rewrite)."""
    if len(sides) == 4 and len(set(sides.values())) == 1:
        value = next(iter(sides.values()))
        return f"{indent}margin:{newline}{indent}  x: {value}{newline}{indent}  y: {value}"
    lines = [f"{indent}margin:"]
    lines += [f"{indent}  {side}: {sides[side]}" for side in ("top", "bottom", "left", "right")
             if side in sides]
    return newline.join(lines)


def fix_typst_margin(text: str, is_metadata: bool = False) -> str:
    """Make a document's or linked --metadata-file's own page-margin
    setting reach Pandoc's Typst template, whichever engine family it was
    actually written for.

    Two distinct problems, both from the same root cause -- ``margin:``
    is a real Pandoc variable for the TYPST template only, and
    ``geometry:`` for the LATEX template only, neither reads the other's
    key at all:

    1. A bare scalar ``margin:`` (``margin: 2.54cm``) is rewritten into
       the ``x:``/``y:`` mapping Typst's template requires -- it always
       renders margin as ``($for(margin/pairs)$...$endfor$)``, iterating
       key/value PAIRS a scalar has none of, so it comes out as the
       literal, invalid ``margin: (: ,)``: a Typst syntax error
       ("unexpected comma") instead of a page margin. Confirmed directly
       (2026-09-28): a document with ``margin: 2.54cm`` and
       ``pdfmd-options: {engine: typst}`` failed outright with exactly
       that error, while rendering fine (albeit at the WRONG margin --
       see frontmatter_margin_geometry_options()) on every LaTeX-family
       engine.

    2. A document with ONLY a ``geometry:`` (no ``margin:`` at all) --
       written for and tested against a LaTeX-family engine -- reaches
       Typst with no margin variable set at all: Typst's template never
       reads ``geometry:``, so it silently falls back to its own built-in
       default (1.25in) instead of erroring, the same "wrong margin, no
       warning" failure frontmatter_margin_geometry_options() fixes in the
       other direction. Parsed via parse_geometry_sides() and added as a
       new ``margin:`` mapping -- ``geometry:`` itself is left in place;
       it's inert for Typst, not harmful.

    Neither fix touches a ``margin:`` that's already a YAML mapping --
    Pandoc's ``/pairs`` filter already turns that straight into valid
    Typst key/value pairs, and it may use Typst's own ``inside``/
    ``outside``/``rest`` keys, which parse_margin_sides() can't safely
    reinterpret but Typst's own template needs no help with anyway.

    `is_metadata` marks a linked --metadata-file (passed by
    prepared_latex_inputs() using its own `doc_count`), which Pandoc
    accepts EITHER fenced (front-matter-shaped, handled the same as a
    document below) OR completely bare -- no ``---``/``...`` delimiters
    at all, just the YAML directly. A bare MAIN document (`is_metadata`
    False) is always left alone instead: with no front matter at all,
    that's markdown BODY text, never YAML, and must never be parsed as
    such.
    """
    front_matter = core.LEADING_FRONT_MATTER_RE.match(text)
    if front_matter:
        block = front_matter.group(1)
        prefix = text[:front_matter.start(1)]
        suffix = text[front_matter.end(1):]
    elif is_metadata:
        block = text
        prefix = ""
        suffix = ""
    else:
        return text
    newline = "\r\n" if "\r\n" in block else "\n"

    if core.yaml is not None:
        try:
            data = core.yaml.safe_load(block)
        except core.yaml.YAMLError:
            data = None
        if isinstance(data, dict) and "margin" not in data and "geometry" in data:
            sides = parse_geometry_sides(data["geometry"])
            if not sides:
                return text
            insertion = sides_to_typst_margin_yaml(sides, "", newline) + newline
            return prefix + insertion + block + suffix
        if isinstance(data, dict) and isinstance(data.get("margin"), dict):
            return text  # already a mapping -- Typst's template handles it as-is

    def replace(match: re.Match) -> str:
        value = match.group("val").strip().strip("'\"")
        if not value or value.startswith(("{", "[")):
            return match.group(0)
        indent = match.group("indent")
        return f"{indent}margin:{newline}{indent}  x: {value}{newline}{indent}  y: {value}"

    fixed_block = TYPST_MARGIN_RE.sub(replace, block, count=1)
    if fixed_block == block:
        return text
    return prefix + fixed_block + suffix


def has_monofont(md_path: Path, variables: list[str], metadata_files=()) -> bool:
    return core.has_font_setting("monofont", md_path, variables, metadata_files)
