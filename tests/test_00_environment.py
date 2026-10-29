"""Not a test: importing it (every module of tests/ is imported before the first test runs) keeps the suite from filling the
cache of the machine with a build record for each of the thousand documents it builds. The tests of the record itself ask for
it (`--build-log on`, or their own cache folder)."""

import os

os.environ.setdefault("PDFMD_BUILD_LOG", "off")
