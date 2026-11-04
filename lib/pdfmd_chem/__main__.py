"""`python3 path/to/pdfmd_chem < request.json`: the LaTeX filter's one call per document (batch.py says what it sends)."""

import sys
from pathlib import Path

if __package__ in (None, ""):                         # run as a folder: its parent holds pdfmd_chem and pdfmd_mhchem
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pdfmd_chem.batch import main
else:
    from .batch import main

raise SystemExit(main())
