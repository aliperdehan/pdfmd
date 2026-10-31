#!/usr/bin/env python3
"""Point Formula/pdfmd.rb at a pdfmd-cli release on PyPI: only the `url` and `sha256` lines of the formula change (its pyyaml and
pypdf resources are pinned by hand and only need touching when pdfmd's own dependencies do).

    python3 scripts/bump_formula.py [VERSION] [--tries N] [--wait SECONDS]

Without a VERSION it takes PyPI's newest. publish.yml runs it right after the upload; PyPI's JSON can lag the upload by a few
seconds, so a version that is not there yet is asked for again (`--tries` times, `--wait` seconds apart). Prints the version the
formula now names, and `unchanged` as a second word when the formula already named it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

FORMULA = Path(__file__).resolve().parent.parent / "Formula" / "pdfmd.rb"


def sdist_of(data: dict) -> dict:
    """The source distribution among the files of one PyPI JSON answer."""
    for item in data["urls"]:
        if item["packagetype"] == "sdist":
            return item
    raise SystemExit("PyPI lists no source distribution for this release")


def rewrite(text: str, url: str, sha256: str) -> str:
    """The formula's text with its own `url` and `sha256` (the two-space-indented ones, not a resource's) replaced."""
    text, urls = re.subn(r'(?m)^  url ".*"$', lambda _: f'  url "{url}"', text, count=1)
    text, sums = re.subn(r'(?m)^  sha256 ".*"$', lambda _: f'  sha256 "{sha256}"', text, count=1)
    if urls != 1 or sums != 1:
        raise SystemExit("the formula has no top-level url and sha256 lines to replace")
    return text


def fetch(version: str | None, tries: int, wait: float) -> dict:
    address = f"https://pypi.org/pypi/pdfmd-cli/{version + '/' if version else ''}json"
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(address) as answer:
                return json.load(answer)
        except urllib.error.HTTPError as error:
            if error.code != 404 or attempt == tries:
                raise SystemExit(f"PyPI answered {error.code} for {address}")
        print(f"PyPI does not list {version} yet (try {attempt} of {tries})", file=sys.stderr)
        time.sleep(wait)
    raise SystemExit("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version", nargs="?", help="a pdfmd-cli version (default: PyPI's newest)")
    parser.add_argument("--tries", type=int, default=12, help="how often to ask PyPI for a release that is not listed yet")
    parser.add_argument("--wait", type=float, default=10.0, help="seconds between two asks")
    args = parser.parse_args(argv)
    data = fetch(args.version, args.tries, args.wait)
    item = sdist_of(data)
    before = FORMULA.read_text(encoding="utf-8")
    after = rewrite(before, item["url"], item["digests"]["sha256"])
    FORMULA.write_text(after, encoding="utf-8")
    print(data["info"]["version"], "unchanged" if after == before else "changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
