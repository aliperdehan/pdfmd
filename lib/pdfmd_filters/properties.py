"""Select the document's written properties and pass display rows to Pandoc."""

from __future__ import annotations

from pathlib import Path

from pdfmd_base import core

# Front matter with a job of its own, omitted by show: true. Explicit
# selection and show: all can still print these keys.
HIDDEN_KEYS = frozenset("""
    pdfmd-options engine priority chapter parts order kit kit-stack alias aliases
    title subtitle author authors date abstract abstract-title title-prefix
    affiliation affiliations institute institution thanks dedication keywords subject
    documentclass class classoption geometry margin fontsize mainfont sansfont
    monofont mathfont CJKmainfont fontfamily fontfamilyoptions mainfontoptions
    sansfontoptions monofontoptions mathfontoptions fontenc linestretch indent
    papersize pagestyle page-numbering lang dir babel-lang babel-otherlangs
    polyglossia-lang polyglossia-otherlangs header-includes include-before
    include-after bibliography biblatexoptions biblio-style biblio-title csl
    citation-style citation-abbreviations citations references nocite link-citations reference-section-title
    citeproc natbib biblatex suppress-bibliography toc toc-title toc-depth
    numbersections number-offset secnumdepth lof lot listings highlighting-macros
    colorlinks linkcolor urlcolor citecolor filecolor toccolor urlstyle
    link-bibliography document-css css template standalone resource-path
    linkReferences figureTitle tableTitle listingTitle subfigGrid listings caption
    header footer output format watermark background pagecolor
    themeoptions beameroption beameroptions section-titles tbl-cap fig-cap
    aspectratio theme colortheme fonttheme innertheme outertheme navigation
    slide-level revealjs-url slidy-url s5-url slideous-url beamerarticle handout
    cssclasses publish permalink position
""".split())

MAP = "tag:yaml.org,2002:map"
SEQ = "tag:yaml.org,2002:seq"
NULL = "tag:yaml.org,2002:null"
DATE = "tag:yaml.org,2002:timestamp"


def written_fields(node, prefix=(), parents=frozenset()):
    """Flatten maps in YAML order, without following recursive YAML aliases."""
    if node.tag != MAP or id(node) in parents or not node.value:
        if prefix:
            yield ".".join(prefix), prefix[0], node, parents
        return
    for key, value in node.value:
        if isinstance(key.value, str):
            yield from written_fields(value, (*prefix, key.value), parents | {id(node)})


def written_value(node, parents, *, tags=False):
    """Use scalar node text, keeping the written boolean and date spelling."""
    if node.tag == NULL or id(node) in parents:
        return ""
    if node.tag == SEQ:
        values = [written_value(value, parents | {id(node)}, tags=tags) for value in node.value]
        return (" " if tags else ", ").join(value for value in values if value)
    if node.tag == MAP:
        return ", ".join(f"{key.value}: {written_value(value, parents | {id(node)})}"
                         for key, value in node.value if isinstance(key.value, str))
    value = node.value if isinstance(node.value, str) else ""
    return "#" + value.lstrip("#") if tags and value else value


def selected_rows(source: Path, metadata: list[Path], no_auto, options: dict) -> list[list]:
    try:
        text = source.read_text(encoding="utf-8-sig")
        front = core.LEADING_FRONT_MATTER_RE.match(text.lstrip("\n"))
        root = core.yaml.compose(front.group("yaml"), Loader=core.yaml.SafeLoader) if front else None
    except (OSError, UnicodeError, core.yaml.YAMLError):
        return []
    if root is None or root.tag != MAP:
        return []

    show = options.get("show")
    rows = {key: (top, node, parents) for key, top, node, parents in written_fields(root)}
    hide = options.get("hide")
    hide = {str(key) for key in hide} if isinstance(hide, list) else set()
    labels = options.get("labels")
    labels = labels if isinstance(labels, dict) else {}
    ordinary = core.option_flag(show) is True
    hidden = HIDDEN_KEYS
    if ordinary:
        kit_keys = set()
        for active in core.active_kits(source, metadata, no_auto):
            keys = active.kit.helper.get("latex-keys")
            if isinstance(keys, (dict, list)):
                kit_keys.update(str(key) for key in keys)
        hidden = hidden.union(kit_keys)
    if isinstance(show, list):
        ordered = dict.fromkeys(key for wanted in map(str, show)
                                for key in rows if key == wanted or key.startswith(wanted + "."))
    else:
        ordered = rows

    result = []
    for key in ordered:
        top, node, parents = rows[key]
        if key in hide or any(key.startswith(name + ".") for name in hide):
            continue
        tags = key == "tags"
        value = written_value(node, parents, tags=tags)
        if ordinary and (top in hidden or top.startswith("pdfmd-") or not value.strip()):
            continue
        label = labels.get(key, key)
        date = node.tag == DATE or key in ("date", "dates") or key.endswith("-date")
        result.append([label if isinstance(label, str) else key, value, tags or date])
    return result


def arguments(source: Path, metadata: list[Path], no_auto) -> list[str]:
    if core.yaml is None or source.suffix.casefold() not in core.MARKDOWN_LIKE_SUFFIXES:
        return []
    properties = core.first_pdfmd_option(source, metadata, "properties")
    if not isinstance(properties, dict):
        return []
    show = properties.get("show")
    if core.option_flag(show) is not True and show != "all" and not isinstance(show, list):
        return []
    rows = selected_rows(source, metadata, no_auto, properties)
    if not rows:
        return []

    import json
    from shutil import copyfile

    from pdfmd_filters import temporary_filter_directory

    try:
        from pdfmd_lua import path
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = path("properties")
    if shipped is None:
        core.pdfmd_lua_missing("properties")
        return []
    directory = Path(temporary_filter_directory("pdfmd-properties-"))
    filter_path = directory / "properties.lua"
    copyfile(shipped, filter_path)
    config = {"rows": rows, "place": str(properties.get("place", "top")),
              "style": str(properties.get("style", "table")),
              "own": "properties" in core.frontmatter_pdfmd_options(source)}
    (directory / "properties.lua.json").write_text(json.dumps(config), encoding="utf-8")
    return ["--lua-filter", str(filter_path)]
