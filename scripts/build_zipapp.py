#!/usr/bin/env python3
"""Build dist/pdfmd.pyz: pdfmd as ONE file, for a machine that cannot `pip install` (no network: a sandbox that only
takes an upload).

    python3 scripts/build_zipapp.py                 # dist/pdfmd.pyz, with PyYAML and pypdf copied in from this Python
    python3 scripts/build_zipapp.py -o /tmp/x.pyz   # elsewhere
    python3 pdfmd.pyz report.md                     # on the other machine: needs Python 3.9+, Pandoc and a PDF engine

The file is a zip with a small launcher. A zip cannot hold what Pandoc has to open as real files (the Lua filters, the
LaTeX headers), so the first run unpacks it into ~/.cache/pdfmd/pyz/<hash>/ and every run after that uses that folder.
PyYAML and pypdf are pure Python and are taken from the Python this script runs in (PyYAML's C speedup is left out);
with neither, pdfmd still builds, but without front matter parsing and PDF stamping.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("pdfmd_direct", "pdfmd_history", "pdfmd_images", "pdfmd_inkmd", "pdfmd_labels", "pdfmd_lua", "pdfmd_office", "pdfmd_setup",
            "pdfmd_tables", "pdfmd_unicode")
DEPENDENCIES = ("yaml", "pypdf")
SKIP_DIRS = {"__pycache__", "tests", "test", ".git"}
SKIP_SUFFIXES = (".so", ".pyd", ".dylib", ".pyc", ".pyo")

LAUNCHER = '''\
"""pdfmd.pyz: unpack once, then run the real pdfmd.py."""
import hashlib, os, shutil, sys, tempfile, zipfile
from pathlib import Path

archive = Path(sys.argv[0]).resolve() if zipfile.is_zipfile(sys.argv[0]) else Path(__file__).resolve().parent
digest = hashlib.sha256(archive.read_bytes()).hexdigest()[:16]
base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")) / "pdfmd" / "pyz"
target = base / digest
if not (target / "pdfmd.py").is_file():
    base.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="unpack-", dir=base))
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if name != "__main__.py":
                bundle.extract(name, scratch)
    try:
        scratch.rename(target)
    except OSError:                       # another run got there first
        shutil.rmtree(scratch, ignore_errors=True)
sys.path.insert(0, str(target))
sys.argv[0] = "pdfmd"
import pdfmd
pdfmd.main()
'''


def add_tree(bundle: zipfile.ZipFile, source: Path, root: Path) -> int:
    count = 0
    for path in sorted(source.rglob("*")):
        if path.is_dir() or any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name.endswith(SKIP_SUFFIXES):
            continue
        bundle.write(path, path.relative_to(root).as_posix())
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--output", type=Path, default=ROOT / "dist" / "pdfmd.pyz")
    parser.add_argument("--no-dependencies", action="store_true", help="do not copy PyYAML and pypdf in")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("__main__.py", LAUNCHER)
        bundle.write(ROOT / "pdfmd.py", "pdfmd.py")
        files = 1
        for package in PACKAGES:
            files += add_tree(bundle, ROOT / package, ROOT)
        for name in ([] if args.no_dependencies else DEPENDENCIES):
            spec = importlib.util.find_spec(name)
            if spec is None or not spec.submodule_search_locations:
                print(f"WARN  {name} is not installed here; the file will work without it (less)", file=sys.stderr)
                continue
            folder = Path(next(iter(spec.submodule_search_locations)))
            files += add_tree(bundle, folder, folder.parent)
    size = args.output.stat().st_size
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()[:16]
    print(f"{args.output}  ({files} files, {size / 1048576:.1f} MB, id {digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
