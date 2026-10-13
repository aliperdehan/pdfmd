"""Packaging is in pyproject.toml. This file only has the build copy the documents into the `pdfmd_docs` package, so that an
installed pdfmd has the README, the recipes, the agent guide and the changelog of its own version (`pdfmd --doc`)."""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

DOCUMENTS = (("README.md", "README.md"), ("CHANGELOG.md", "CHANGELOG.md"), ("docs/recipes.md", "recipes.md"),
             ("docs/agents.md", "agents.md"))


class BuildPy(build_py):
    def run(self):
        super().run()
        root = Path(__file__).resolve().parent
        target = Path(self.build_lib) / "pdfmd_docs"
        target.mkdir(parents=True, exist_ok=True)
        for source, name in DOCUMENTS:
            if (root / source).is_file():
                shutil.copyfile(root / source, target / name)


setup(cmdclass={"build_py": BuildPy})
