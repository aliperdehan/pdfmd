"""Which font names a Word document can rely on. A `.docx` carries font *names*, not fonts: the person
who opens it has Times New Roman, not STIX Two Text. `office_font()` maps a font the PDF uses to
the closest one every Word has, and says when it did."""

from __future__ import annotations

SERIF = "Times New Roman"
SANS = "Arial"
MONO = "Consolas"

_SERIF_NAMES = {"stix two text", "stix two math", "stix", "stixgeneral", "stix general", "libertinus serif",
                "libertinus", "latin modern roman", "lmroman10", "computer modern", "cmu serif", "noto serif",
                "pt serif", "source serif 4", "source serif pro", "charter", "linux libertine", "linux libertine o",
                "tex gyre termes", "nimbus roman", "times", "dejavu serif", "gentium", "gentium plus",
                "garamond", "eb garamond", "crimson text", "crimson pro", "lora", "amiri"}
_SANS_NAMES = {"helvetica", "helvetica neue", "inter", "source sans 3", "source sans pro", "fira sans",
               "noto sans", "open sans", "lato", "roboto", "tex gyre heros", "nimbus sans", "dejavu sans",
               "latin modern sans", "sf pro", "sf pro text", "avenir", "avenir next", "gill sans", "segoe ui"}
_MONO_NAMES = {"jetbrains mono", "fira code", "fira mono", "source code pro", "menlo", "monaco", "sf mono",
               "dejavu sans mono", "inconsolata", "ibm plex mono", "lucida console", "latin modern mono",
               "tex gyre cursor", "nimbus mono", "courier", "andale mono", "roboto mono", "cascadia code"}
UNIVERSAL = {"times new roman", "arial", "calibri", "cambria", "consolas", "courier new", "georgia", "verdana",
             "tahoma", "trebuchet ms", "palatino linotype", "book antiqua", "cambria math", "symbol",
             "segoe ui", "aptos", "comic sans ms", "impact", "century gothic", "garamond"}


def office_font(name: str | None, role: str = "main", policy: str = "safe") -> tuple[str | None, str | None]:
    """(font to write, note). `policy` 'exact' keeps the name; 'safe' maps well-known fonts that Word
    does not ship to Times New Roman / Arial / Consolas; a font nobody has heard of is kept, with a note."""
    if not name:
        return None, None
    name = str(name).strip()
    key = name.casefold()
    if policy == "exact" or key in UNIVERSAL:
        return name, None
    for names, replacement in ((_SERIF_NAMES, SERIF), (_SANS_NAMES, SANS), (_MONO_NAMES, MONO)):
        if key in names:
            return replacement, f"{name} -> {replacement} (Word has no {name}; office: {{fonts: exact}} keeps it)"
    return name, f"{name} is not a font every Word has; the reader's Word will substitute one if it is missing"
