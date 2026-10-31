"""`python3 path/to/pdfmd_smiles < request.json`: the filter's one call per document (batch.py says what it sends)."""

import sys
from pathlib import Path

if __package__ in (None, ""):                         # run as a folder: its parent holds pdfmd_smiles
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pdfmd_smiles.batch import main
else:
    from .batch import main

raise SystemExit(main())
