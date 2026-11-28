"""Explicit fetch of a Pandoc template or CSL style from an index, repository or link."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urlsplit

from pdfmd_base import core
from pdfmd_config.installed_styles import save_style


GITHUB_API = "https://api.github.com/repos"
GITHUB_RAW = "https://raw.githubusercontent.com"
TEMPLATE_INDEX = (GITHUB_API + "/Wandmalfarbe/pandoc-templates.org/contents/src/_data/templates-unprocessed.json")
CSL_REPOSITORY = "citation-style-language/styles"
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SPDX = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9.+-]+(?:[ \t]+(?:AND|OR|WITH)[ \t]+[A-Za-z0-9.+-]+)*)")
TEMPLATE_SUFFIXES = frozenset({".asciidoc", ".asciidoctor", ".beamer", ".commonmark", ".commonmark_x", ".context",
                              ".docbook", ".docbook4", ".docbook5", ".docx", ".dzslides", ".epub", ".epub2", ".epub3",
                              ".gfm", ".html", ".html4", ".html5", ".icml", ".jats", ".jats_archiving", ".jats_articleauthoring",
                              ".jats_publishing", ".latex", ".man", ".markdown", ".mediawiki", ".ms", ".odt", ".opml",
                              ".org", ".pptx", ".revealjs", ".rst", ".rtf", ".s5", ".slideous", ".slidy", ".texinfo",
                              ".textile", ".typst"})
# An upper bound on an untrusted HTTP response, including GitHub's recursive tree and the template index.
MAX_RESPONSE = 32 * 1024 * 1024


class InstallError(ValueError):
    pass


@dataclass(frozen=True)
class Asset:
    filename: str
    source: str
    revision: str
    licence: str
    data: bytes


def download(url: str) -> bytes:
    from urllib.request import Request

    request = Request(url, headers={"User-Agent": f"pdfmd/{core.PDFMD_VERSION}"})
    with core.open_url(request, 20) as response:
        data = response.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise InstallError(f"response too large at {url}")
    return data


def json_response(url: str):
    return json.loads(download(url))


def index_repository(name: str) -> str:
    index = json_response(TEMPLATE_INDEX)
    entries = json.loads(base64.b64decode(index["content"]))
    for entry in entries:
        if entry["id"] == name:
            repository = entry.get("github_repository")
            if isinstance(repository, str):
                repository = repository.removeprefix("https://github.com/").rstrip("/").removesuffix(".git")
                if REPOSITORY.fullmatch(repository):
                    return repository
            raise InstallError(f"the index lists no GitHub repository for {name!r}; supply the asset URL")
    raise InstallError(f"no template named {name!r} in the pandoc-templates.org index")


def path_parts(path: str) -> list[str]:
    parts = path.split("/")
    if any(not part or part in (".", "..") or "\\" in part or ":" in part for part in parts):
        raise InstallError(f"invalid asset path {path!r}")
    return parts


def selected_path(tree: dict, kind: str, requested: str, basename: str = "") -> str:
    suffixes = {".csl"} if kind == "csl" else TEMPLATE_SUFFIXES
    blobs = [PurePosixPath(item["path"]) for item in tree["tree"]
             if item["type"] == "blob" and item.get("mode") != "120000"]
    if requested:
        if PurePosixPath(requested) not in blobs or (kind == "csl" and PurePosixPath(requested).suffix.lower() != ".csl"):
            raise InstallError(f"no {kind} asset at {requested!r}")
        return requested
    if tree.get("truncated"):
        raise InstallError("GitHub truncated the repository tree; supply #ASSET-PATH")
    matches = sorted(path.as_posix() for path in blobs
                     if path.suffix.lower() in suffixes and (not basename or path.name == basename))
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise InstallError("several assets match; specify #ASSET-PATH ("
                           + ", ".join(matches) + ")")
    raise InstallError(f"no {kind} assets in the repository")


def style_data(kind: str, url: str) -> bytes:
    if kind != "csl":
        return download(url)
    text, why = core.fetch_csl(url)
    if text is None:
        raise InstallError(f"{url}: {why}")
    return text.encode("utf-8")


def asset_licence(kind: str, data: bytes) -> str:
    if kind == "csl":
        from xml.etree import ElementTree

        root = ElementTree.fromstring(data)
        rights = root.find("{*}info/{*}rights")
        if rights is not None:
            return rights.get("license") or " ".join("".join(rights.itertext()).split())
    match = SPDX.search(data.decode("utf-8", errors="replace"))
    return match[1] if match else ""


def from_repository(kind: str, repository: str, ref: str, path: str, *, basename: str = "") -> Asset:
    if not REPOSITORY.fullmatch(repository):
        raise InstallError(f"invalid GitHub repository {repository!r}")
    api = f"{GITHUB_API}/{repository}"
    project = json_response(api)
    head = json_response(f"{api}/commits/{quote(ref or project['default_branch'], safe='')}")
    revision = head["sha"]
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise InstallError("GitHub returned an invalid commit SHA")
    tree = head["commit"]["tree"]["sha"]
    if re.fullmatch(r"[0-9a-f]{40}", tree) is None:
        raise InstallError("GitHub returned an invalid tree SHA")
    path = selected_path(json_response(f"{api}/git/trees/{tree}?recursive=1"), kind, path, basename)
    filename = path_parts(path)[-1]
    url = f"{GITHUB_RAW}/{repository}/{revision}/{quote(path)}"
    data = style_data(kind, url)
    licence = asset_licence(kind, data)
    if not licence:
        from urllib.error import HTTPError

        try:
            licence = json_response(f"{api}/license?ref={revision}")["license"]["spdx_id"] or ""
        except HTTPError as error:
            if error.code != 404:
                raise
            error.close()
    return Asset(filename, url, revision, licence, data)


def resolve(kind: str, source: str) -> Asset:
    link = urlsplit(source)
    if link.scheme in ("http", "https") and link.hostname:
        path = unquote(link.path).strip("/")
        parts = path.split("/")
        if link.hostname == "github.com" and len(parts) >= 5 and parts[2] in ("blob", "raw"):
            return from_repository(kind, "/".join(parts[:2]), parts[3], "/".join(parts[4:]))
        if link.hostname == "raw.githubusercontent.com" and len(parts) >= 4:
            return from_repository(kind, "/".join(parts[:2]), parts[2], "/".join(parts[3:]))
        if link.hostname == "github.com" and len(parts) == 2:
            return from_repository(kind, path.removesuffix(".git"), "", unquote(link.fragment))
        filename = path_parts(parts[-1])[-1]
        if kind == "csl" and not filename.lower().endswith(".csl"):
            filename += ".csl"
        data = style_data(kind, source)
        return Asset(filename, source, "sha256:" + hashlib.sha256(data).hexdigest(), asset_licence(kind, data), data)

    location, _, path = source.partition("#")
    name, _, ref = location.partition("@")
    if kind == "template" and not REPOSITORY.fullmatch(name):
        name = index_repository(name)
    elif kind == "csl" and not REPOSITORY.fullmatch(name):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
            raise InstallError("supply a CSL style name, repository or URL")
        basename = name if name.endswith(".csl") else name + ".csl"
        return from_repository(kind, CSL_REPOSITORY, ref, path, basename=basename)
    return from_repository(kind, name, ref, path)


def install_style(kind: str, source: str, assume_yes: bool) -> bool:
    from xml.etree.ElementTree import ParseError

    if not source:
        print(f"Use --install {kind}:SOURCE (append #ASSET-PATH when a repository has several assets).")
        return True
    try:
        asset = resolve(kind, source)
        if asset.licence in ("", "NOASSERTION", "NONE"):
            raise InstallError(f"cannot identify the licence of {asset.source}")
        print(f"Source: {asset.source}\nRevision: {asset.revision}\nLicence: {asset.licence}", flush=True)
        from pdfmd_setup.userpath import confirm

        interactive = sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get("PDFMD_NO_PROMPT")
        if not confirm(f"Install this {kind}? [y/N] ", assume_yes, print, input, interactive):
            return False
        path = save_style(kind, source, asset.filename, asset.source, asset.revision, asset.licence, asset.data)
        print(f"Installed {kind}: {core.display_path(path)}")
    except (OSError, ValueError, KeyError, TypeError, ParseError, EOFError) as error:
        print(f"ERROR  --install {kind}: {error}", file=sys.stderr)
        return False
    return True
