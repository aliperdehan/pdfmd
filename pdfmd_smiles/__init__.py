"""Chemical structures written as text: a SMILES string, a molfile (MDL .mol, .sdf), a Tripos .mol2 or an InChI, drawn as a
picture (v3.31.42; pdfmd_lua/smiles.lua finds the blocks, `python3 pdfmd_smiles` draws them, one call for a document).

    ```smiles                             ::: smiles                            ```{.smiles caption="Aspirin"}
    CC(=O)Oc1ccccc1C(=O)O                 CC(=O)Oc1ccccc1C(=O)O                 CC(=O)Oc1ccccc1C(=O)O
    ```                                   :::                                   ```

A block holds one structure per line, side by side under one caption; a name after the SMILES (`CCO ethanol`, the .smi
convention) is written under that structure. `file="x.mol"` takes the structure from a file instead of the body. The
settings (`pdfmd-options.smiles`, every one also a block attribute) are DEFAULTS below; a number that changes the drawing is
a setting, never a constant in the code.
"""

from __future__ import annotations

import re

VERSION = 1                     # part of every picture's cache key: raise it when the drawing code changes

# `pdfmd-options.smiles` and the attributes of a block (the same names). `columns` is the attribute name of `per-row`.
DEFAULTS: dict = {"engine": "auto", "format": "auto", "office-format": "png", "cell-width": 250, "cell-height": 200,
                  "per-row": 3, "dpi": 300, "bond-length": 40, "palette": "color"}
ENGINES = ("auto", "rdkit")
FORMATS = ("auto", "svg", "png", "pdf")
OFFICE_FORMATS = ("png", "svg")
PALETTES = ("color", "bw")
KINDS = ("auto", "smiles", "mol", "mol2", "inchi")
NUMBERS = ("cell-width", "cell-height", "per-row", "dpi", "bond-length")
ALIASES = {"columns": "per-row", "per_row": "per-row", "cell_width": "cell-width", "cell_height": "cell-height",
           "office_format": "office-format", "bond_length": "bond-length"}

EXTENSIONS = {".mol": "mol", ".mdl": "mol", ".sdf": "mol", ".sd": "mol", ".mol2": "mol2", ".smi": "smiles",
              ".smiles": "smiles", ".inchi": "inchi", ".txt": "smiles"}


class SmilesError(Exception):
    pass


def normalise(options: dict | None, where: str) -> dict:
    """The settings of `options` (a mapping of names, aliases allowed), checked; only the names given are returned."""
    if options is None:
        return {}
    if not isinstance(options, dict):
        raise SmilesError(f"{where} must be a mapping of settings ({', '.join(DEFAULTS)})")
    chosen: dict = {}
    for name, value in options.items():
        key = ALIASES.get(str(name), str(name))
        if key not in DEFAULTS:
            raise SmilesError(f"{where}: unknown setting {name!r}; the settings are {', '.join(DEFAULTS)}")
        if key in NUMBERS:
            try:
                number = int(str(value).strip())
            except ValueError:
                raise SmilesError(f"{where}: {key} must be a whole number, not {value!r}") from None
            if number < 1:
                raise SmilesError(f"{where}: {key} must be at least 1, not {number}")
            chosen[key] = number
        else:
            word = str(value).strip().casefold()
            allowed = {"engine": ENGINES, "format": FORMATS, "office-format": OFFICE_FORMATS, "palette": PALETTES}[key]
            if word not in allowed:
                raise SmilesError(f"{where}: {key} {value!r}: choose one of {', '.join(allowed)}")
            chosen[key] = word
    return chosen


def resolve(options: dict | None) -> dict:
    """Every setting, the defaults filled in, for `pdfmd-options.smiles`."""
    return {**DEFAULTS, **normalise(options, "pdfmd-options.smiles")}


def detect_kind(text: str, kind: str = "auto", extension: str = "") -> str:
    """What `text` is written in: the `kind` asked for, else the file's extension, else what the text looks like."""
    if kind != "auto":
        return kind
    if extension.lower() in EXTENSIONS and extension.lower() != ".txt":
        return EXTENSIONS[extension.lower()]
    if re.search(r"(?m)^M\s+END\s*$", text) or "$$$$" in text:
        return "mol"
    if "@<TRIPOS>MOLECULE" in text:
        return "mol2"
    if re.match(r"\s*InChI=", text):
        return "inchi"
    return "smiles"


def split_molecules(text: str, kind: str) -> list[tuple[str, str]]:
    """(text of one structure, its name) for each structure in `text`, a molfile or SD file per record, a line each for
    SMILES and InChI (a name after the first space)."""
    if kind == "mol":
        # a molfile's first line is its title and may be blank, so a record keeps its leading lines as they are
        records = [record for record in re.split(r"(?m)^\$\$\$\$[ \t]*$\n?", text) if re.search(r"(?m)^M\s+END", record)]
        return [(record.rstrip("\n") + "\n", "") for record in records]
    if kind == "mol2":
        pieces = re.split(r"(?m)^(?=@<TRIPOS>MOLECULE)", text)
        return [(piece, "") for piece in pieces if piece.strip()]
    found = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        head, _, name = line.partition(" ") if kind == "smiles" else (line, "", "")
        found.append((head, name.strip()))
    return found
