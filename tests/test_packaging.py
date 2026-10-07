"""Guards on what `pip install pdfmd-cli` ships and declares.

v3.20.0 once dropped `dependencies = ["pyyaml", "pypdf"]` from pyproject.toml
while adding the extras; every test still passed on a machine that happened to
have both installed, and only CI (which installs what is declared) noticed.
These read pyproject.toml itself, so that cannot go unnoticed again.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

try:
    import tomllib
except ImportError:  # Python 3.10
    tomllib = None


def requirement_name(requirement: str) -> str:
    """'pymd2pdf>=0.6,<0.7; python_version >= "3.11"' -> 'pymd2pdf'."""
    return re.match(r"[A-Za-z0-9_.-]+", requirement.strip()).group(0).lower().replace("_", "-")


def load_pyproject() -> dict:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(text)
    return {"project": _project_without_toml(text)}  # pragma: no cover -- 3.10 only


def _project_without_toml(text: str) -> dict:  # pragma: no cover -- 3.10 only
    """Just enough of the file for these tests when tomllib is not there."""
    def array(body: str) -> list[str]:
        return re.findall(r'"([^"]+)"', body)

    project = re.search(r"^\[project\]\n(.*?)(?=^\[)", text, re.S | re.M).group(1)
    extras = re.search(r"^\[project\.optional-dependencies\]\n(.*?)(?=^\[)", text, re.S | re.M).group(1)
    setuptools = re.search(r"^\[tool\.setuptools\]\n(.*?)(?=^\[)", text, re.S | re.M).group(1)
    package_data = re.search(r"^\[tool\.setuptools\.package-data\]\n(.*?)(?=^\[|\Z)", text, re.S | re.M).group(1)

    def key(body: str, name: str) -> list[str]:
        found = re.search(rf"^{re.escape(name)}\s*=\s*\[(.*?)\]", body, re.S | re.M)
        return array(found.group(1)) if found else []

    return {
        "dependencies": key(project, "dependencies"),
        "license-files": key(project, "license-files"),
        "optional-dependencies": {name: key(extras, name) for name in re.findall(r"^(\w[\w-]*)\s*=", extras, re.M)},
        "_setuptools": {"py-modules": key(setuptools, "py-modules"), "packages": key(setuptools, "packages"),
                        "package-data": {"pdfmd_inkmd": key(package_data, "pdfmd_inkmd")}},
    }


class PyprojectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_pyproject()
        cls.project = cls.data["project"]
        cls.setuptools = cls.data.get("tool", {}).get("setuptools") or cls.project.get("_setuptools", {})

    def test_runtime_dependencies_are_declared(self):
        declared = {requirement_name(item) for item in self.project.get("dependencies", [])}
        self.assertTrue({"pyyaml", "pypdf"} <= declared, f"declared: {sorted(declared)}")

    def test_every_install_kind_with_a_package_has_a_matching_extra(self):
        extras = self.project["optional-dependencies"]
        for kind, specs in pdfmd.INSTALL_SPECS.items():
            self.assertIn(kind, extras, f"pdfmd --install {kind} has no pdfmd-cli[{kind}] extra")
            wanted = {requirement_name(spec) for spec in specs}
            declared = {requirement_name(item) for item in extras[kind]}
            self.assertEqual(wanted, declared, kind)

    def test_the_vendored_package_and_its_licences_are_shipped(self):
        self.assertIn("pdfmd", self.setuptools["py-modules"])
        self.assertIn("pdfmd_inkmd", self.setuptools["packages"])
        package_data = self.setuptools["package-data"]["pdfmd_inkmd"]
        self.assertIn("assets/fonts/*", package_data)
        self.assertIn("LICENSE", package_data)
        licences = self.project["license-files"]
        self.assertIn("pdfmd_inkmd/LICENSE", licences)
        self.assertIn("pdfmd_inkmd/assets/fonts/DejaVuSans-LICENSE.txt", licences)
        for name in ("LICENSE", "assets/fonts/DejaVuSans.ttf", "assets/fonts/DejaVuSans-LICENSE.txt"):
            self.assertTrue((ROOT / "pdfmd_inkmd" / name).is_file(), name)

    def test_the_changelog_starts_with_the_current_version(self):
        headings = re.findall(r"^## v(\d+\.\d+\.\d+)\b", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
        self.assertEqual(headings[0], pdfmd.PDFMD_VERSION)


@unittest.skipIf(tomllib is None, "tomllib is not there; the fallback is what the tests above ran on")
class FallbackParserTests(unittest.TestCase):
    """The Python 3.10 path (no tomllib) must read the same things, or CI on 3.10
    would be checking something other than the 3.13 run does."""

    def test_the_fallback_agrees_with_tomllib(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        real = tomllib.loads(text)
        fallback = _project_without_toml(text)
        self.assertEqual(fallback["dependencies"], real["project"]["dependencies"])
        self.assertEqual(fallback["license-files"], real["project"]["license-files"])
        self.assertEqual(fallback["optional-dependencies"], real["project"]["optional-dependencies"])
        self.assertEqual(fallback["_setuptools"]["py-modules"], real["tool"]["setuptools"]["py-modules"])
        self.assertEqual(fallback["_setuptools"]["packages"], real["tool"]["setuptools"]["packages"])
        self.assertEqual(fallback["_setuptools"]["package-data"],
                         {"pdfmd_inkmd": real["tool"]["setuptools"]["package-data"]["pdfmd_inkmd"]})


if __name__ == "__main__":
    unittest.main()
