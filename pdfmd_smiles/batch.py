"""One process for a whole document: pdfmd_lua/smiles.lua sends every `smiles` block it meets in one JSON request on stdin
and reads the answers on stdout (`python3 pdfmd_smiles`, see __main__.py), so RDKit is imported once.

Request: {"cache": "<folder of pictures>", "settings": {...pdfmd_smiles.DEFAULTS, resolved}, "target": "tex" | "html" |
"typst" | "office" | "md", "items": [{"text": "<the block's body or file>", "extension": ".mol" | "", "attributes": {"caption":
..., "engine": ..., "kind": ..., "columns": ...}}]}.
The answer is a list, one entry per item: {"file": path, "width": px, "height": px, "format": "svg|png|pdf", "count": n} or
{"error": "<why>"}. A picture is kept in the cache folder under a key made of everything that changes it: the engine, the
engine's version, the kind, the structures, the format, the cell size, the columns, the dpi (and VERSION of this module),
so a changed setting or another engine never finds a stale picture, and the same block drawn twice is drawn once.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import (DEFAULTS, KINDS, SmilesError, VERSION, detect_kind, normalise, split_molecules)


def _rdkit():
    try:
        import rdkit
        from rdkit import Chem, RDLogger
        from rdkit.Chem.Draw import rdMolDraw2D
    except ImportError:
        raise SmilesError("RDKit is not installed for the Python that runs pdfmd (pip install rdkit)") from None
    RDLogger.DisableLog("rdApp.*")             # an unreadable SMILES is reported in the answer, not on stderr
    return rdkit, Chem, rdMolDraw2D


def choose_format(target: str, settings: dict) -> str:
    """The picture format for the output: the setting when it says one, else what the writer reads best."""
    if settings["format"] != "auto":
        return settings["format"]
    return {"tex": "pdf", "html": "svg", "typst": "svg", "office": settings["office-format"], "md": "svg"}.get(target, "svg")


def read_molecule(Chem, kind: str, text: str):
    if kind == "smiles":
        mol = Chem.MolFromSmiles(text)
    elif kind == "mol":
        mol = Chem.MolFromMolBlock(text)
    elif kind == "mol2":
        mol = Chem.MolFromMol2Block(text)
    elif kind == "inchi":
        if not hasattr(Chem, "MolFromInchi"):
            raise SmilesError("this RDKit has no InChI support")
        mol = Chem.MolFromInchi(text)
    else:
        raise SmilesError(f"unknown kind {kind!r}")
    if mol is None:
        shown = text.strip().splitlines()[0][:60] if text.strip() else ""
        raise SmilesError(f"RDKit could not read the {kind} structure {shown!r}")
    return mol


def _convert_to_pdf(svg_text: str, out: Path) -> bool:
    tool = shutil.which("rsvg-convert")
    if not tool:
        return False
    with tempfile.TemporaryDirectory(prefix="pdfmd-smiles") as folder:
        source = Path(folder) / "in.svg"
        source.write_text(svg_text, encoding="utf-8")
        done = subprocess.run([tool, "-f", "pdf", "-o", str(out), str(source)], capture_output=True)
    return done.returncode == 0 and out.is_file() and out.stat().st_size > 0


def draw_one(item: dict, base: dict, cache: Path, target: str) -> dict:
    attributes = item.get("attributes") or {}
    settings = {**base, **normalise({k: v for k, v in attributes.items() if k in DEFAULTS or k in ("columns",)},
                                    "a smiles block")}
    engine = settings["engine"]
    if engine not in ("auto", "rdkit"):
        raise SmilesError(f"engine {engine!r} is not available")
    kind = str(attributes.get("kind", "auto")).strip().casefold()
    if kind not in KINDS:
        raise SmilesError(f"kind {kind!r}: choose one of {', '.join(KINDS)}")
    text = item.get("text") or ""
    if not text.strip():
        raise SmilesError("the block is empty (write a SMILES, or file=\"...\")")
    kind = detect_kind(text, kind, item.get("extension") or "")
    molecules = split_molecules(text, kind)
    if not molecules:
        raise SmilesError("the block holds no structure")
    fmt = choose_format(target, settings)
    rdkit, Chem, rdMolDraw2D = _rdkit()
    key = hashlib.sha1(json.dumps({"v": VERSION, "engine": "rdkit", "engine-version": rdkit.__version__, "kind": kind,
                                   "molecules": molecules, "format": fmt, "cell": [settings["cell-width"], settings["cell-height"]],
                                   "per-row": settings["per-row"], "dpi": settings["dpi"],
                                   "bond-length": settings["bond-length"]},
                                  sort_keys=True).encode("utf-8")).hexdigest()[:24]
    count = len(molecules)
    columns = min(count, settings["per-row"])
    rows = math.ceil(count / columns)
    cell_w, cell_h = settings["cell-width"], settings["cell-height"]
    width, height = columns * cell_w, rows * cell_h
    cache.mkdir(parents=True, exist_ok=True)
    answer = {"width": width, "height": height, "count": count}
    kept = cache / f"smiles-{key}.{fmt}"
    if kept.is_file() and kept.stat().st_size > 0:
        return {**answer, "file": str(kept), "format": fmt}
    mols = [read_molecule(Chem, kind, source) for source, _ in molecules]
    legends = [name for _, name in molecules] if any(name for _, name in molecules) else None
    if fmt == "png":
        scale = settings["dpi"] / 96.0
        drawer = rdMolDraw2D.MolDraw2DCairo(int(width * scale), int(height * scale), int(cell_w * scale), int(cell_h * scale))
    else:
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height, cell_w, cell_h)
    drawer.drawOptions().clearBackground = False
    drawer.drawOptions().fixedBondLength = settings["bond-length"] * (settings["dpi"] / 96.0 if fmt == "png" else 1)
    drawer.DrawMolecules(mols, legends=legends)
    drawer.FinishDrawing()
    data = drawer.GetDrawingText()
    if fmt == "pdf":
        out = cache / f"smiles-{key}.pdf"
        if _convert_to_pdf(data, out):
            return {**answer, "file": str(out), "format": "pdf"}
        return draw_one({**item, "attributes": {**attributes, "format": "png"}}, base, cache, target)
    out = cache / f"smiles-{key}.{fmt}"
    if isinstance(data, str):
        out.write_text(data, encoding="utf-8")
    else:
        out.write_bytes(data)
    return {**answer, "file": str(out), "format": fmt}


def main(stream_in=None, stream_out=None) -> int:
    request = json.load(stream_in or sys.stdin)
    try:
        base = {**DEFAULTS, **normalise(request.get("settings"), "pdfmd-options.smiles")}
    except SmilesError as error:
        json.dump([{"error": str(error)} for _ in request.get("items", [])], stream_out or sys.stdout)
        return 0
    cache = Path(request["cache"])
    target = request.get("target", "tex")
    answers = []
    for item in request.get("items", []):
        try:
            answers.append(draw_one(item, base, cache, target))
        except SmilesError as error:
            answers.append({"error": str(error)})
        except Exception as error:               # a drawing fault must leave the block as code, never stop the build
            answers.append({"error": f"{type(error).__name__}: {error}"})
    json.dump(answers, stream_out or sys.stdout)
    return 0
