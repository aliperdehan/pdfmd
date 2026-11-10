"""Not a test: what every test module does first (tests/isolation_support.py): the run gets its own cache, config and data
folders, and no build records (`PDFMD_BUILD_LOG=off`; the tests of the record ask for it, `--build-log on` or their own cache
folder). Kept, as the first module a discovery imports, from when only a whole-suite run went through it."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)
