"""`pdfmd --install KIND`: the pip packages of a kind (`INSTALL_SPECS`, `install_extra`), and the tools pdfmd fetches itself, each
checked against a SHA-256: Typst's and Tectonic's release binaries (`install_typst`, `install_tectonic`, from GitHub's release list:
`github_release_asset`, `release_asset_matching`), node (`install_node`), KaTeX and MathJax for the math of WeasyPrint's PDFs
(`install_katex`, `install_mathjax`), D2 and Graphviz as WebAssembly (`install_diagram`), Calibre (`install_calibre`), the kits of a
repository (`install_kits`) and the fonts (`install_fonts`); with the argparse types of `--install` and `--uninstall` (`install_kind`,
`uninstall_kind`).

Moved out of `pdfmd.py` unchanged (v3.33.35, SPLIT.md), with `INSTALL_SPECS`, the `TYPST_*`, `TECTONIC_*`, `D2_*`, `GRAPHVIZ_*` and
`NODE_*` tables, `KATEX_SHA256`, `KATEX_KEPT`, `MATHJAX_REGISTRY`, `MATHJAX_SOURCE_SHA256`, `MATHJAX_FONT_SIZES`, the
`MATHJAX_BUNDLE_*` lists, `DIAGRAM_INSTALLS`, `CALIBRE_REPOSITORY` and `KIT_SOURCES_DEFAULT`. `core` is the `pdfmd` module, bound by
`pdfmd.py` when it loads (the first binding wins); the pdfmd names the code uses (`INSTALL_KINDS`, `INSTALL_SIZES`, `KATEX_VERSION`,
`KATEX_PACKAGE`, `MATHJAX_DEFAULT_FONT`, `MATHJAX_FONT_SHA256`, `MATHJAX_VERSION`, `PDFMD_VERSION`, `batchocr_spec`,
`batchocr_version`, `config_options`, `data_root`, `display_path`, `find_batchocr`, `fonts_directory`, `install_ocr_languages`,
`install_ocr_tools`, `kits_install_directory`, `mathjax_font_package`, `open_url`, `own_python_folder`, `reset_font_caches`,
`resolve_calibre`, `run_probe`, `system_install_hint`, `tools_directory`, `typst_version`, `unicode_module`, `use_managed_tools` and
`which`) are read as `core.X` when it runs. `TYPST_MIN` and `typst_too_old` (v3.33.62) are new here: the oldest Typst pdfmd builds
with, and the line that says the one found is older. `KATEX_PACKAGE` stays in `pdfmd.py`: it is built from `KATEX_VERSION` when that file is loaded. Tests patch
`download_file`, `github_latest_release`, `github_release_asset`, `install_extra`, `install_tectonic`, `install_typst`,
`typst_asset_name` and `d2_asset_name` of this package as `pdfmd.X` (and `config_options`, `data_root`, `resolve_calibre`, `run_probe`
and `which`): every use of them here is `core.X`, so a patch reaches it. `urllib.request` is imported inside the functions that
fetch (start-up time, v3.32.55); `tarfile` and `zipfile` are imported at the top, as they were in `pdfmd.py` (which still imports
`zipfile` itself and no longer imports `tarfile`; both load at start, as before).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile, mkdtemp

from pdfmd_base import core


# `pdfmd --install KIND` / `pdfmd-cli[KIND]`; the version ranges match the
# vendored inkmd and the md2pdf this code was written against.
INSTALL_SPECS = {
    "translit": ["pypinyin", "anyascii"],
    "emoji": ["inkmd>=0.5,<0.6"],
    "math": ["pymd2pdf>=0.6,<0.7", "matplotlib"],
    "pandoc": ["pypandoc_binary"],
    "tui": ["prompt_toolkit>=3"],
}


TYPST_REPOSITORY = "typst/typst"
TYPST_TARGETS = {
    ("linux", "x86_64"): "x86_64-unknown-linux-musl", ("linux", "aarch64"): "aarch64-unknown-linux-musl",
    ("darwin", "x86_64"): "x86_64-apple-darwin", ("darwin", "aarch64"): "aarch64-apple-darwin",
    ("windows", "x86_64"): "x86_64-pc-windows-msvc", ("windows", "aarch64"): "aarch64-pc-windows-msvc",
}


# The oldest Typst pdfmd builds with (v3.33.62), a version fact: `par.spacing` (the space between paragraphs, `indent: true`,
# paragraph-spacing) and a `set document` in the body (a title or authors kept for the PDF's properties) are Typst 0.12's.
TYPST_MIN = (0, 12)


def typst_too_old() -> str | None:
    """The line that says the `typst` found is older than TYPST_MIN, and where a newer one comes from; None for a current one,
    for none found and for one that says no version. `typst_version()` is cached, so asking again (the build record asks too)
    starts no second process. An engine too old is treated as one that is missing: `-e typst` stops with this line, a list
    (`-e typst,lualatex`) goes on to the next with it as a NOTE, and the automatic chain passes Typst over (SKIP) when it
    gets there."""
    version = core.typst_version()
    if version == (0,) or version >= TYPST_MIN:
        return None
    found = core.which("typst")
    own = found is not None and Path(found).resolve().parent == core.tools_directory().resolve()
    advice = ("`pdfmd --install typst` puts a current one in its place" if own else
              f"update it ({core.display_path(Path(found)) if found else 'typst'}; github.com/{TYPST_REPOSITORY}/releases), "
              "or take it off PATH and run `pdfmd --install typst`")
    return (f"Typst {'.'.join(map(str, version))} is older than {'.'.join(map(str, TYPST_MIN))}, which pdfmd needs: "
            + advice)


def typst_asset_name(system: str | None = None, machine: str | None = None) -> str | None:
    """The file name of Typst's release archive for this machine, or None."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    target = TYPST_TARGETS.get((system, machine))
    if target is None:
        return None
    return f"typst-{target}.zip" if system == "windows" else f"typst-{target}.tar.xz"


def github_release_asset(repository: str, name: str) -> tuple[str, str | None]:
    """(download URL, SHA-256 or None) of a release asset of the latest release.
    GitHub lists a digest for each asset; without the API (offline, rate limit)
    the stable `latest/download` link is used and nothing can be checked."""
    import urllib.request  # here, not at the top: only this needs it (start-up time, v3.32.55)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"pdfmd/{core.PDFMD_VERSION}"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        request = urllib.request.Request(f"https://api.github.com/repos/{repository}/releases/latest",
                                         headers=headers)
        with core.open_url(request, 30) as response:
            release = json.load(response)
        for asset in release["assets"]:
            if asset["name"] == name:
                digest = str(asset.get("digest") or "")
                return asset["browser_download_url"], (digest.split(":", 1)[1] if digest.startswith("sha256:") else None)
    except (OSError, ValueError, KeyError):
        pass
    return f"https://github.com/{repository}/releases/latest/download/{name}", None


def download_file(url: str, destination: Path, sha256: str | None) -> None:
    """Download url to destination, refusing a file whose SHA-256 is not the expected one."""
    import urllib.request  # here, not at the top: only this needs it (start-up time, v3.32.55)
    request = urllib.request.Request(url, headers={"User-Agent": f"pdfmd/{core.PDFMD_VERSION}"})
    digest = hashlib.sha256()
    with core.open_url(request, 120) as response, destination.open("wb") as handle:
        for chunk in iter(lambda: response.read(1 << 20), b""):
            digest.update(chunk)
            handle.write(chunk)
    if sha256 and digest.hexdigest() != sha256.lower():
        destination.unlink(missing_ok=True)
        raise OSError(f"SHA-256 mismatch for {url}: expected {sha256}, got {digest.hexdigest()}")


def extract_executable(archive: Path, wanted: str, destination: Path, inside: str = "") -> Path:
    """Write the one file called ``wanted`` out of a .zip / .tar.xz into ``destination``; with ``inside`` (`bin`), the
    one in a folder of that name."""
    def chosen(name: str) -> bool:
        path = PurePosixPath(name)
        return path.name == wanted and (not inside or path.parent.name == inside)

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            member = next((name for name in bundle.namelist() if chosen(name)), None)
            data = bundle.read(member) if member else None
    else:
        with tarfile.open(archive) as bundle:
            found = next((item for item in bundle.getmembers() if item.isfile() and chosen(item.name)), None)
            data = bundle.extractfile(found).read() if found else None
    if data is None:
        raise OSError(f"{wanted} is not in {archive.name}")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / wanted
    temporary = target.with_name(target.name + ".part")
    temporary.write_bytes(data)
    temporary.chmod(0o755)
    temporary.replace(target)
    return target


def install_typst() -> bool:
    """Download Typst's release binary for this machine into tools_directory()."""
    name = core.typst_asset_name()
    if name is None:
        print(f"No Typst release is listed for {platform.system()} {platform.machine()}; "
              f"see https://github.com/{TYPST_REPOSITORY}/releases", file=sys.stderr)
        return False
    url, sha256 = core.github_release_asset(TYPST_REPOSITORY, name)
    print(f"INSTALL  typst ({core.INSTALL_SIZES['typst']}): {url}")
    executable = "typst.exe" if name.endswith(".zip") else "typst"
    try:
        with NamedTemporaryFile(suffix=Path(name).suffix if name.endswith(".zip") else ".tar.xz",
                                delete=False) as temporary:
            archive = Path(temporary.name)
        try:
            core.download_file(url, archive, sha256)
            print(f"SHA-256 verified ({sha256[:12]}..., as listed by GitHub for this release)" if sha256
                  else "NOTE  no checksum was available for this download, so it could not be verified")
            target = extract_executable(archive, executable, core.tools_directory())
        finally:
            archive.unlink(missing_ok=True)
    except (OSError, tarfile.TarError, zipfile.BadZipFile, ImportError) as error:
        print(f"Could not install Typst ({error}). Install it yourself: {core.system_install_hint()}",
              file=sys.stderr)
        return False
    core.use_managed_tools()
    version = core.run_probe([str(target), "--version"])
    if version is None or version.returncode != 0:
        print(f"Typst was downloaded to {target} but does not run here: {version.stderr.strip() if version else 'it does not answer'}",
              file=sys.stderr)
        return False
    print(f"Installed {version.stdout.strip()} in {core.tools_directory()} "
          "(used when no other Typst is on PATH; delete the file to remove it).")
    return True


KATEX_SHA256 = "78174318fa53363e4321ac3c10b39d3598aaa73a92dc75362eb08b16f6705782"
KATEX_KEPT = ("katex.min.js", "katex.min.css", "contrib/mhchem.min.js")
NODE_DIST = "https://nodejs.org/dist"
NODE_TARGETS = {
    ("linux", "x86_64"): "linux-x64", ("linux", "aarch64"): "linux-arm64",
    ("darwin", "x86_64"): "darwin-x64", ("darwin", "aarch64"): "darwin-arm64",
    ("windows", "x86_64"): "win-x64", ("windows", "aarch64"): "win-arm64",
}


def node_install_hint() -> str:
    if sys.platform == "darwin":
        return "brew install node"
    if sys.platform == "win32":
        return "winget install OpenJS.NodeJS.LTS"
    return "sudo apt install nodejs (or your package manager)"


def node_asset_name(version: str, system: str | None = None, machine: str | None = None) -> str | None:
    """The file name of node's release archive for this machine (`node-v24.21.0-darwin-arm64.tar.xz`), or None."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    target = NODE_TARGETS.get((system, machine))
    if target is None:
        return None
    return f"node-{version}-{target}.zip" if system == "windows" else f"node-{version}-{target}.tar.xz"


def install_node() -> bool:
    """node's newest long-term-support release for this machine into tools_directory(), checked against the SHA-256
    nodejs.org lists for it."""
    import urllib.request  # here, not at the top: only this needs it (start-up time, v3.32.55)
    headers = {"User-Agent": f"pdfmd/{core.PDFMD_VERSION}"}
    try:
        with core.open_url(urllib.request.Request(f"{NODE_DIST}/index.json", headers=headers), 30) as response:
            version = next(str(item["version"]) for item in json.load(response) if item.get("lts"))
        name = node_asset_name(version)
        if name is None:
            print(f"No node release is listed for {platform.system()} {platform.machine()}. Install node yourself: "
                  f"{node_install_hint()}", file=sys.stderr)
            return False
        with core.open_url(urllib.request.Request(f"{NODE_DIST}/{version}/SHASUMS256.txt", headers=headers), 30) as response:
            sums = response.read().decode("utf-8", "replace")
        sha256 = next((line.split()[0] for line in sums.splitlines() if line.split()[1:] == [name]), None)
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f"Could not read node's release list ({error}). Install node yourself: {node_install_hint()}",
              file=sys.stderr)
        return False
    url = f"{NODE_DIST}/{version}/{name}"
    print(f"INSTALL  node {version} (about 30 MB download, 120 MB on disk): {url}")
    executable = "node.exe" if name.endswith(".zip") else "node"
    try:
        with NamedTemporaryFile(suffix=".zip" if name.endswith(".zip") else ".tar.xz", delete=False) as temporary:
            archive = Path(temporary.name)
        try:
            core.download_file(url, archive, sha256)
            print(f"SHA-256 verified ({sha256[:12]}..., as listed by nodejs.org for this release)" if sha256
                  else "NOTE  no checksum was available for this download, so it could not be verified")
            target = extract_executable(archive, executable, core.tools_directory(),
                                        inside="" if executable == "node.exe" else "bin")
        finally:
            archive.unlink(missing_ok=True)
    except (OSError, tarfile.TarError, zipfile.BadZipFile, ImportError) as error:
        print(f"Could not install node ({error}). Install it yourself: {node_install_hint()}", file=sys.stderr)
        return False
    core.use_managed_tools()
    ran = core.run_probe([str(target), "--version"])
    if ran is None or ran.returncode != 0:
        print(f"node was downloaded to {target} but does not run here ({(ran.stderr.strip() or ran.returncode) if ran else 'it does not answer'}). "
              f"Install it yourself: {node_install_hint()}", file=sys.stderr)
        return False
    print(f"Installed node {ran.stdout.strip()} in {core.tools_directory()} (used when no other node is on PATH; delete "
          "the file to remove it).")
    return True


def unpack_katex(archive: Path, target: Path) -> None:
    """KaTeX's npm package into ``target``: KATEX_KEPT, the fonts and the licence, nothing else."""
    staging = target.with_name(target.name + ".part")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            parts = PurePosixPath(member.name).parts
            if not member.isfile() or ".." in parts or len(parts) < 2 or parts[0] != "package":
                continue
            if parts[1:] == ("LICENSE",):
                relative = parts[1:]
            elif parts[1] == "dist" and ("/".join(parts[2:]) in KATEX_KEPT
                                         or (len(parts) == 4 and parts[2] == "fonts")):
                relative = parts[2:]
            else:
                continue
            handle = bundle.extractfile(member)
            if handle is None:
                continue
            destination = staging.joinpath(*relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(handle.read())
    if not all((staging / name).is_file() for name in KATEX_KEPT[:2]) or not list((staging / "fonts").glob("*.woff2")):
        shutil.rmtree(staging, ignore_errors=True)
        raise OSError(f"{archive.name} does not have KaTeX's script, stylesheet and fonts")
    if target.exists():
        shutil.rmtree(target)
    staging.replace(target)


def katex_works(node: str, folder: Path) -> str | None:
    """None when node typesets a formula with the KaTeX in ``folder`` through pdfmd_lua/katex.cjs, else why not."""
    try:
        import pdfmd_lua
    except ImportError:
        return "pdfmd_lua, the folder of pdfmd's filters, is not installed beside pdfmd.py"
    script = pdfmd_lua.FILTERS / "katex.cjs"
    request = json.dumps({"dir": str(folder), "items": [{"tex": "x^2", "display": False}]})
    try:
        ran = subprocess.run([node, str(script)], input=request, capture_output=True, text=True, encoding="utf-8",
                             timeout=60)
        answer = json.loads(ran.stdout)[0] if ran.returncode == 0 else {"error": ran.stderr.strip()[-300:]}
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as error:
        return str(error)
    return None if "katex" in str(answer.get("html", "")) else str(answer.get("error") or answer)


def install_katex() -> bool:
    """`pdfmd --install math:katex`: KaTeX's files, and node when there is none, so that WeasyPrint typesets math."""
    target = core.data_root() / "katex" / core.KATEX_VERSION
    print(f"INSTALL  KaTeX {core.KATEX_VERSION} (about 1.5 MB): {core.KATEX_PACKAGE}")
    try:
        with NamedTemporaryFile(suffix=".tgz", delete=False) as temporary:
            archive = Path(temporary.name)
        try:
            core.download_file(core.KATEX_PACKAGE, archive, KATEX_SHA256)
            unpack_katex(archive, target)
        finally:
            archive.unlink(missing_ok=True)
    except (OSError, tarfile.TarError) as error:
        print(f"Could not install KaTeX ({error}).", file=sys.stderr)
        return False
    print(f"SHA-256 verified ({KATEX_SHA256[:12]}..., pinned in pdfmd for KaTeX {core.KATEX_VERSION})")
    node = core.which("node")
    if node is None:
        print(f"NOTE  KaTeX runs with node, which is not on PATH: pdfmd fetches node's own release (a package manager "
              f"would do too: {node_install_hint()})")
        if not install_node():
            return False
        node = core.which("node")
        if node is None:
            return False
    problem = katex_works(node, target)
    if problem:
        print(f"KaTeX was installed in {target} but node ({node}) could not typeset with it: {problem}",
              file=sys.stderr)
        return False
    print(f"Installed KaTeX {core.KATEX_VERSION} in {target} (delete the folder to remove it): a PDF made by WeasyPrint "
          f"now typesets its math, with node {node}.")
    return True


MATHJAX_REGISTRY = "https://registry.npmjs.org/@mathjax"
MATHJAX_SOURCE_SHA256 = "4611bed26b338dfc4b5757b8ed2d7ba82a85bcbd05d2729fb3465fba17b8896c"
MATHJAX_FONT_SIZES = {"stix2": "4.8 MB"}
MATHJAX_BUNDLE_KEPT = ("node-main.cjs", "node-main.js", "node-main.mjs", "node-main-setup.cjs", "package.json", "core.js",
                       "loader.js", "startup.js", "require.mjs", "output/chtml.js")
MATHJAX_BUNDLE_FOLDERS = ("input/tex", "adaptors")
MATHJAX_BUNDLE_INPUT = ("input/tex.js", "input/tex-base.js")


def mathjax_package_url(package: str) -> str:
    return f"{MATHJAX_REGISTRY}/{package}/-/{package}-{core.MATHJAX_VERSION}.tgz"


def unpack_npm(archive: Path, target: Path, keep) -> int:
    """The files of an npm package (``package/...`` in the archive) that ``keep(parts)`` accepts, into ``target``; how many."""
    count = 0
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            parts = PurePosixPath(member.name).parts
            if not member.isfile() or ".." in parts or len(parts) < 2 or parts[0] != "package" or not keep(parts[1:]):
                continue
            handle = bundle.extractfile(member)
            if handle is None:
                continue
            destination = target.joinpath(*parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(handle.read())
            count += 1
    return count


def mathjax_keeps_source(parts: tuple[str, ...]) -> bool:
    """MathJax's own package: the TeX input, the CHTML output and what loads them (the bundle), not the sources, the
    other outputs, the accessibility and speech code (5 MB), nor the other input languages."""
    relative = "/".join(parts)
    if relative in ("package.json", "LICENSE"):
        return True
    if parts[0] != "bundle":
        return False
    inside = "/".join(parts[1:])
    return (inside in MATHJAX_BUNDLE_KEPT or inside in MATHJAX_BUNDLE_INPUT
            or any(inside.startswith(folder + "/") for folder in MATHJAX_BUNDLE_FOLDERS))


def mathjax_keeps_font(parts: tuple[str, ...]) -> bool:
    """A math font package: its CHTML script and fonts (woff2 and the ranges loaded on demand), its licence."""
    return parts[0] in ("package.json", "chtml.js") or parts[0].startswith("LICENSE") or (parts[0] == "chtml" and len(parts) > 1)


def install_mathjax_files(target: Path, fonts: tuple[str, ...], fetch=None) -> None:
    """MathJax's package and each font's into ``target``/node_modules/@mathjax, each archive checked against its pinned
    SHA-256 (``fetch(url, path, sha256)`` is download_file unless a test gives another)."""
    fetch = fetch or core.download_file
    modules = target / "node_modules" / "@mathjax"
    staging = target.with_name(target.name + ".part")
    shutil.rmtree(staging, ignore_errors=True)
    wanted = [("src", mathjax_package_url("src"), MATHJAX_SOURCE_SHA256, mathjax_keeps_source)]
    wanted += [(core.mathjax_font_package(font), mathjax_package_url(core.mathjax_font_package(font)), core.MATHJAX_FONT_SHA256[font],
                mathjax_keeps_font) for font in fonts]
    for name, url, sha256, keep in wanted:
        if name != "src" and (modules / name / "chtml.js").is_file():
            continue                                  # a font an earlier install put here
        with NamedTemporaryFile(suffix=".tgz", delete=False) as temporary:
            archive = Path(temporary.name)
        try:
            fetch(url, archive, sha256)
            if unpack_npm(archive, staging / "node_modules" / "@mathjax" / name, keep) == 0:
                raise OSError(f"{name} has none of the files pdfmd needs")
        finally:
            archive.unlink(missing_ok=True)
    # an earlier install's other fonts stay: move the new ones in
    for folder in (staging / "node_modules" / "@mathjax").iterdir():
        destination = modules / folder.name
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        folder.replace(destination)
    shutil.rmtree(staging, ignore_errors=True)


def mathjax_works(node: str, folder: Path, font: str) -> str | None:
    """None when node typesets a formula with the MathJax in ``folder`` through pdfmd_lua/mathjax.cjs, else why not."""
    try:
        import pdfmd_lua
    except ImportError:
        return "pdfmd_lua, the folder of pdfmd's filters, is not installed beside pdfmd.py"
    request = json.dumps({"dir": str(folder), "font": font, "items": [{"tex": "\\hat{x}^2", "display": False}]})
    try:
        ran = subprocess.run([node, str(pdfmd_lua.FILTERS / "mathjax.cjs")], input=request, capture_output=True, text=True,
                             encoding="utf-8", timeout=120)
        answer = json.loads(ran.stdout)["answers"][0] if ran.returncode == 0 else {"error": ran.stderr.strip()[-300:]}
    except (OSError, ValueError, KeyError, IndexError, subprocess.TimeoutExpired) as error:
        return str(error)
    return None if "mjx-container" in str(answer.get("html", "")) else str(answer.get("error") or answer)


def ensure_node(what: str) -> str | None:
    """node's path: the one on PATH, else pdfmd fetches node's own release (as for Typst); None when neither works."""
    node = core.which("node")
    if node is None:
        print(f"NOTE  {what} runs with node, which is not on PATH: pdfmd fetches node's own release (a package manager "
              f"would do too: {node_install_hint()})")
        if not install_node():
            return None
        node = core.which("node")
    return node


def install_mathjax() -> bool:
    """`pdfmd --install math:mathjax`: MathJax's files and the STIX Two math font, and node when there is none, so that
    WeasyPrint's PDFs have their math typeset by MathJax."""
    fonts = (core.MATHJAX_DEFAULT_FONT,)
    target = core.data_root() / "mathjax" / core.MATHJAX_VERSION
    size = ", ".join(f"{name} {MATHJAX_FONT_SIZES[name]}" for name in fonts)
    print(f"INSTALL  MathJax {core.MATHJAX_VERSION} and the math fonts {', '.join(fonts)} (downloads: 7.5 MB and {size}; "
          f"about 1 MB on disk for MathJax and 1 MB per font): {MATHJAX_REGISTRY}")
    try:
        install_mathjax_files(target, fonts)
    except (OSError, tarfile.TarError) as error:
        print(f"Could not install MathJax ({error}).", file=sys.stderr)
        return False
    print("SHA-256 verified (pinned in pdfmd for MathJax " + core.MATHJAX_VERSION + ")")
    node = ensure_node("MathJax")
    if node is None:
        return False
    problem = mathjax_works(node, target, fonts[0])
    if problem:
        print(f"MathJax was installed in {target} but node ({node}) could not typeset with it: {problem}", file=sys.stderr)
        return False
    print(f"Installed MathJax {core.MATHJAX_VERSION} in {target} (delete the folder to remove it): a PDF made by WeasyPrint "
          f"now has its math typeset by MathJax (KaTeX, when installed, takes what MathJax cannot read), with node {node}.")
    return True


# -- Diagram tools: D2 and Graphviz (v3.28.32) --------------------------------------------------------------------------
# A ```d2 or ```dot block is drawn by the tool that reads it (pdfmd_lua/diagram.lua). `pdfmd --install diagram:d2` puts
# D2's own release binary in pdfmd's tools folder, as for Typst (GitHub lists a SHA-256 for every asset). Graphviz has no
# download of its own for macOS or Linux, so `pdfmd --install diagram:dot` fetches @hpcc-js/wasm-graphviz (Graphviz built
# to WebAssembly, one 2 MB script, the SHA-256 below) and writes `dot`, `neato`, ... launchers that run it with node
# (pdfmd_lua/graphviz.cjs); node comes the way it does for KaTeX. It writes SVG only: for a PDF or a PNG diagram.lua
# converts that SVG, as for D2, which takes rsvg-convert or inkscape. The tools folder is last on PATH, so a Graphviz or D2
# you installed yourself is the one that runs.
D2_REPOSITORY = "terrastruct/d2"
D2_TARGETS = {
    ("linux", "x86_64"): "linux-amd64", ("linux", "aarch64"): "linux-arm64",
    ("darwin", "x86_64"): "macos-amd64", ("darwin", "aarch64"): "macos-arm64",
    ("windows", "x86_64"): "windows-amd64", ("windows", "aarch64"): "windows-arm64",
}
GRAPHVIZ_VERSION = "1.29.2"
GRAPHVIZ_SHA256 = "fbabf5f7a085f37009477d3585b2da1e4960f99dda54004e69c20553c8d172df"
GRAPHVIZ_PACKAGE = f"https://registry.npmjs.org/@hpcc-js/wasm-graphviz/-/wasm-graphviz-{GRAPHVIZ_VERSION}.tgz"
GRAPHVIZ_COMMANDS = ("dot", "neato", "fdp", "sfdp", "circo", "twopi", "osage", "patchwork")
DIAGRAM_INSTALLS = ("d2", "dot")


def d2_asset_name(tag: str, system: str | None = None, machine: str | None = None) -> str | None:
    """The file name of D2's release archive for this machine at release ``tag`` (v0.9.0), or None."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    target = D2_TARGETS.get((system, machine))
    return f"d2-{tag}-{target}.tar.gz" if target else None


def github_latest_release(repository: str) -> dict:
    """The latest release of a GitHub repository as the API gives it (tag_name, assets with their digests)."""
    import urllib.request  # here, not at the top: only this needs it (start-up time, v3.32.55)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"pdfmd/{core.PDFMD_VERSION}"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with core.open_url(urllib.request.Request(f"https://api.github.com/repos/{repository}/releases/latest",
                                         headers=headers), 30) as response:
        return json.load(response)


def install_d2() -> bool:
    """`pdfmd --install diagram:d2`: D2's release binary for this machine into tools_directory()."""
    try:
        release = core.github_latest_release(D2_REPOSITORY)
        tag = str(release["tag_name"])
        name = core.d2_asset_name(tag)
        asset = next((item for item in release["assets"] if item["name"] == name), None) if name else None
    except (OSError, ValueError, KeyError) as error:
        print(f"Could not read D2's release list ({error}). Install it yourself: https://d2lang.com/tour/install",
              file=sys.stderr)
        return False
    if asset is None:
        print(f"No D2 release is listed for {platform.system()} {platform.machine()}; "
              f"see https://github.com/{D2_REPOSITORY}/releases", file=sys.stderr)
        return False
    digest = str(asset.get("digest") or "")
    sha256 = digest.split(":", 1)[1] if digest.startswith("sha256:") else None
    print(f"INSTALL  D2 {tag} (about 17 MB download): {asset['browser_download_url']}")
    executable = "d2.exe" if platform.system().lower() == "windows" else "d2"
    try:
        with NamedTemporaryFile(suffix=".tar.gz", delete=False) as temporary:
            archive = Path(temporary.name)
        try:
            core.download_file(asset["browser_download_url"], archive, sha256)
            print(f"SHA-256 verified ({sha256[:12]}..., as listed by GitHub for this release)" if sha256
                  else "NOTE  no checksum was available for this download, so it could not be verified")
            target = extract_executable(archive, executable, core.tools_directory(), inside="bin")
        finally:
            archive.unlink(missing_ok=True)
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"Could not install D2 ({error}). Install it yourself: https://d2lang.com/tour/install", file=sys.stderr)
        return False
    core.use_managed_tools()
    ran = core.run_probe([str(target), "--version"])
    if ran is None or ran.returncode != 0:
        print(f"D2 was downloaded to {target} but does not run here: {ran.stderr.strip() if ran else 'it does not answer'}", file=sys.stderr)
        return False
    print(f"Installed D2 {ran.stdout.strip()} in {core.tools_directory()} (used when no other d2 is on PATH; delete the file "
          "to remove it). A PDF or Word diagram is converted from D2's SVG by rsvg-convert or inkscape.")
    return True


def unpack_graphviz(archive: Path, target: Path) -> None:
    """wasm-graphviz's npm package into ``target``: dist/index.js, package.json and the licence, nothing else."""
    staging = target.with_name(target.name + ".part")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            parts = PurePosixPath(member.name).parts
            if not member.isfile() or ".." in parts or len(parts) < 2 or parts[0] != "package":
                continue
            if parts[1:] not in (("LICENSE",), ("package.json",), ("dist", "index.js")):
                continue
            handle = bundle.extractfile(member)
            if handle is None:
                continue
            destination = staging.joinpath(*parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(handle.read())
    if not (staging / "dist" / "index.js").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise OSError(f"{archive.name} does not have wasm-graphviz's script")
    if target.exists():
        shutil.rmtree(target)
    staging.replace(target)


def write_graphviz_launchers(folder: Path, script: Path, destination: Path) -> list[Path]:
    """`dot`, `neato`, ... in ``destination``, each running pdfmd_lua/graphviz.cjs (copied to ``folder``) with node:
    the node beside the launcher (pdfmd's own), else the one on PATH."""
    made = []
    destination.mkdir(parents=True, exist_ok=True)
    runner = folder / "graphviz.cjs"
    shutil.copyfile(script, runner)
    for name in GRAPHVIZ_COMMANDS:
        if sys.platform == "win32":
            path = destination / f"{name}.cmd"
            path.write_text(f'@echo off\r\nset "NODE=node"\r\nif exist "%~dp0node.exe" set "NODE=%~dp0node.exe"\r\n'
                            f'"%NODE%" "{runner}" --lib "{folder}" --engine {name} %*\r\n', encoding="utf-8")
        else:
            path = destination / name
            path.write_text('#!/bin/sh\n# written by pdfmd --install diagram:dot (Graphviz as WebAssembly, run by node)\n'
                            'here=$(cd "$(dirname "$0")" && pwd)\nnode="$here/node"\n[ -x "$node" ] || node=node\n'
                            f'exec "$node" "{runner}" --lib "{folder}" --engine {name} "$@"\n', encoding="utf-8")
            path.chmod(0o755)
        made.append(path)
    return made


def install_graphviz() -> bool:
    """`pdfmd --install diagram:dot`: Graphviz as WebAssembly, run by node (fetched when there is none)."""
    try:
        import pdfmd_lua
    except ImportError:
        print("ERROR  --install diagram:dot needs the pdfmd_lua package (a full install of pdfmd-cli).", file=sys.stderr)
        return False
    target = core.data_root() / "graphviz" / GRAPHVIZ_VERSION
    print(f"INSTALL  Graphviz {GRAPHVIZ_VERSION} as WebAssembly (about 2 MB): {GRAPHVIZ_PACKAGE}")
    try:
        with NamedTemporaryFile(suffix=".tgz", delete=False) as temporary:
            archive = Path(temporary.name)
        try:
            core.download_file(GRAPHVIZ_PACKAGE, archive, GRAPHVIZ_SHA256)
            unpack_graphviz(archive, target)
        finally:
            archive.unlink(missing_ok=True)
        launchers = write_graphviz_launchers(target, pdfmd_lua.FILTERS / "graphviz.cjs", core.tools_directory())
    except (OSError, tarfile.TarError) as error:
        print(f"Could not install Graphviz ({error}). Install it yourself: brew install graphviz | apt install graphviz",
              file=sys.stderr)
        return False
    print(f"SHA-256 verified ({GRAPHVIZ_SHA256[:12]}..., pinned in pdfmd for wasm-graphviz {GRAPHVIZ_VERSION})")
    if core.which("node") is None:
        print(f"NOTE  Graphviz runs with node, which is not on PATH: pdfmd fetches node's own release (a package manager "
              f"would do too: {node_install_hint()})")
        if not install_node():
            return False
    core.use_managed_tools()
    try:
        ran = subprocess.run([str(launchers[0]), "-Tsvg"], input="digraph { a -> b }", capture_output=True, encoding="utf-8", errors="replace",
                             timeout=60, env={**os.environ, "PATH": os.pathsep.join(
                                 [str(core.tools_directory()), os.environ.get("PATH", "")])})
    except (OSError, subprocess.TimeoutExpired) as error:
        ran = None
        problem = str(error)
    else:
        problem = ran.stderr.strip()[-300:]
    if ran is None or ran.returncode != 0 or "<svg" not in ran.stdout:
        print(f"Graphviz was installed in {target} but did not draw a graph here: {problem}", file=sys.stderr)
        return False
    print(f"Installed Graphviz {GRAPHVIZ_VERSION} in {target}: `dot`, `neato` and the other layout commands are in "
          f"{core.tools_directory()} (used when no other is on PATH; delete them and the folder to remove). They write SVG; a "
          "PDF or Word diagram is converted from it by rsvg-convert or inkscape.")
    return True


def install_diagram(which_one: str = "") -> bool:
    """`--install diagram` (both), `diagram:d2`, `diagram:dot`."""
    wanted = [which_one] if which_one else list(DIAGRAM_INSTALLS)
    done = True
    for name in wanted:
        done = (install_d2() if name == "d2" else install_graphviz()) and done
    return done


# -- Calibre (v3.29.3): `pdfmd --install calibre` ------------------------------------------------------------------------
# Calibre (GPLv3) is a program pdfmd runs, never one it contains; it is fetched on request only. Nothing is installed
# without being asked, and a download is refused unless GitHub lists its SHA-256. macOS: the release's disk image is
# mounted read-only and calibre.app copied into ~/Applications (where resolve_calibre looks). Linux: the release's .txz is
# unpacked into data_root()/calibre/<version> (no root, no desktop files). Windows: winget (the installer wants admin
# rights, which pdfmd does not take). The package manager is offered first (brew, winget) in a terminal.
CALIBRE_REPOSITORY = "kovidgoyal/calibre"


def calibre_asset_pattern(system: str | None = None, machine: str | None = None) -> str | None:
    """The regular expression of Calibre's release file for this machine (`calibre-9.16.0.dmg`), or None."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    if system == "darwin":
        return r"calibre-[\d.]+\.dmg"
    if system == "linux" and machine in ("x86_64", "aarch64"):
        return r"calibre-[\d.]+-" + ("arm64" if machine == "aarch64" else "x86_64") + r"\.txz"
    return None


def calibre_release_asset(pattern: str, release: dict | None = None) -> tuple[str, str, str] | None:
    """(file name, URL, SHA-256) of Calibre's latest release's file matching `pattern` (see release_asset_matching)."""
    return release_asset_matching(CALIBRE_REPOSITORY, pattern, release)


def release_asset_matching(repository: str, pattern: str, release: dict | None = None) -> tuple[str, str, str] | None:
    """(file name, URL, SHA-256) of the latest release's file matching `pattern`, None when GitHub lists no such file or
    no digest for it (the API is the only source of the checksum: no download is made without one). For releases whose
    file names carry the version."""
    import urllib.request  # here, not at the top: only this needs it (start-up time, v3.32.55)
    if release is None:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": f"pdfmd/{core.PDFMD_VERSION}"}
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
        try:
            request = urllib.request.Request(f"https://api.github.com/repos/{repository}/releases/latest", headers=headers)
            with core.open_url(request, 30) as response:
                release = json.load(response)
        except (OSError, ValueError):
            return None
    for asset in release.get("assets", []):
        if re.fullmatch(pattern, str(asset.get("name", ""))):
            digest = str(asset.get("digest") or "")
            if digest.startswith("sha256:"):
                return asset["name"], asset["browser_download_url"], digest.split(":", 1)[1]
    return None


def calibre_package_manager() -> list[str] | None:
    """The command of the system's package manager that installs Calibre and needs no administrator password, or None."""
    if sys.platform == "darwin" and core.which("brew"):
        return ["brew", "install", "--cask", "calibre"]
    if sys.platform == "win32" and core.which("winget"):
        return ["winget", "install", "--id", "calibre.calibre", "-e"]
    return None


def calibre_install_hint() -> str:
    if sys.platform == "darwin":
        return "brew install --cask calibre"
    if sys.platform == "win32":
        return "winget install --id calibre.calibre -e"
    return "sudo apt install calibre (or your package manager), or calibre-ebook.com/download_linux"


def safe_unpack_tar(archive: Path, target: Path) -> None:
    """Unpack a .tar.xz into `target`, refusing a member that would land outside it (absolute, `..`, a link out)."""
    root = target.resolve()
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            destination = (root / member.name).resolve()
            if destination != root and root not in destination.parents:
                raise OSError(f"{archive.name}: {member.name} would be written outside the folder")
            if member.issym() or member.islnk():
                link = (destination.parent / member.linkname).resolve() if member.issym() else (root / member.linkname).resolve()
                if link != root and root not in link.parents:
                    raise OSError(f"{archive.name}: {member.name} links outside the folder")
        target.mkdir(parents=True, exist_ok=True)
        bundle.extractall(target)


def detach_disk_image(mount: Path, attempts: int = 4, pause: float = 1.0) -> bool:
    """`hdiutil detach` for a mounted image, tried `attempts` times with a pause between (macOS answers "resource busy" for a
    moment after a copy, e.g. while Spotlight looks at the volume), then once with -force. True when it is detached."""
    for attempt in range(attempts):
        if attempt:
            time.sleep(pause)
        if subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True).returncode == 0:
            return True
    return subprocess.run(["hdiutil", "detach", "-force", str(mount)], capture_output=True).returncode == 0


def install_calibre_dmg(image: Path, applications: Path) -> Path:
    """Mount Calibre's disk image read-only and copy calibre.app into `applications` (replacing a copy there);
    returns the app's ebook-convert."""
    mount = Path(mkdtemp(prefix="pdfmd-calibre-dmg-"))
    attached = False
    try:
        done = subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noverify", "-mountpoint", str(mount), str(image)],
                              capture_output=True, encoding="utf-8", errors="replace")
        if done.returncode != 0:
            raise OSError("hdiutil could not open the disk image: " + (done.stderr.strip().splitlines() or ["?"])[-1])
        attached = True
        app = mount / "calibre.app"
        if not app.is_dir():
            raise OSError("calibre.app is not in the disk image")
        applications.mkdir(parents=True, exist_ok=True)
        destination = applications / "calibre.app"
        if destination.exists():
            shutil.rmtree(destination)
        copied = subprocess.run(["ditto", str(app), str(destination)], capture_output=True, encoding="utf-8", errors="replace")
        if copied.returncode != 0:
            raise OSError("ditto could not copy calibre.app: " + (copied.stderr.strip().splitlines() or ["?"])[-1])
    finally:
        if attached:
            detach_disk_image(mount)
        shutil.rmtree(mount, ignore_errors=True)
    return destination / "Contents" / "MacOS" / "ebook-convert"


def install_calibre(fetch=None, release: dict | None = None, applications: Path | None = None,
                    interactive: bool | None = None, find=None) -> bool:
    """`pdfmd --install calibre`. `fetch(url, destination, sha256)`, `release` (GitHub's JSON), `applications` (macOS),
    `interactive` and `find` (what says Calibre is there) are for the tests."""
    present = (find or core.resolve_calibre)()
    if present:
        print(f"OK    Calibre is already installed: {present}")
        return True
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get("PDFMD_NO_PROMPT")
    manager = calibre_package_manager()
    if manager and interactive:
        command_text = " ".join(manager)
        try:
            answer = input(f"Install Calibre with `{command_text}`? [Y/n/d = download it myself] ").strip().casefold()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer in ("", "y", "yes"):
            try:
                ran = subprocess.run(manager).returncode == 0
            except OSError as error:
                print(f"Could not run {manager[0]} ({error}).", file=sys.stderr)
                ran = False
            if ran:
                found = core.resolve_calibre()
                if found:
                    print(f"Installed Calibre: {found}")
                    return True
            print(f"{command_text} did not give a Calibre pdfmd can find.", file=sys.stderr)
            return False
        if answer not in ("d", "download"):
            return False
    if sys.platform == "win32" or calibre_asset_pattern() is None:
        print(f"pdfmd does not unpack Calibre on this system ({platform.system()} {platform.machine()}): "
              f"{calibre_install_hint()}", file=sys.stderr)
        return False
    pattern = calibre_asset_pattern()
    asset = calibre_release_asset(pattern, release)
    if asset is None:
        print("GitHub lists no Calibre download for this machine with a SHA-256 (offline, or a rate limit?), so none is made "
              f"unchecked. Install it with {calibre_install_hint()}", file=sys.stderr)
        return False
    name, url, sha256 = asset
    version = re.search(r"calibre-([\d.]+?)(?:-|\.dmg|\.txz)", name)
    version_text = version.group(1) if version else "latest"
    print(f"INSTALL  Calibre {version_text} ({core.INSTALL_SIZES['calibre']}): {url}")
    fetch = fetch or core.download_file
    with NamedTemporaryFile(suffix=Path(name).suffix, delete=False) as temporary:
        archive = Path(temporary.name)
    try:
        fetch(url, archive, sha256)
        print(f"SHA-256 verified ({sha256[:12]}..., as listed by GitHub for this release)")
        if sys.platform == "darwin":
            target = install_calibre_dmg(archive, applications or Path.home() / "Applications")
        else:
            folder = core.data_root() / "calibre" / version_text
            if folder.exists():
                shutil.rmtree(folder)
            safe_unpack_tar(archive, folder)
            target = folder / "ebook-convert"
    except (OSError, tarfile.TarError) as error:
        print(f"Could not install Calibre ({error}). Install it yourself: {calibre_install_hint()}", file=sys.stderr)
        return False
    finally:
        archive.unlink(missing_ok=True)
    environment = dict(os.environ)
    if sys.platform != "win32":
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        ran = subprocess.run([str(target), "--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=120, env=environment)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Calibre was unpacked to {target} but does not run here: {error}", file=sys.stderr)
        return False
    if ran.returncode != 0:
        print(f"Calibre was unpacked to {target} but does not run here: {ran.stderr.strip()[-300:]}", file=sys.stderr)
        return False
    print(f"Installed {ran.stdout.strip().splitlines()[0] if ran.stdout.strip() else 'Calibre'} at {target} "
          f"(pdfmd finds it there; delete {'calibre.app' if sys.platform == 'darwin' else 'the folder'} to remove it).")
    return True


# -- Tectonic: the other core (v3.29.7) -----------------------------------------------------------------------------------
# `pdfmd --install full` is Pandoc and Typst. `pdfmd --install core:tex` (also `cortex`) is Pandoc and Tectonic, the
# self-contained LaTeX engine (one binary; it fetches the TeX files a document needs, once, from the network): the release
# file for the machine, checked against the SHA-256 GitHub lists, its `tectonic` placed in pdfmd's tools folder.
TECTONIC_REPOSITORY = "tectonic-typesetting/tectonic"
TECTONIC_TARGETS = {
    ("linux", "x86_64"): "x86_64-unknown-linux-musl", ("linux", "aarch64"): "aarch64-unknown-linux-musl",
    ("darwin", "x86_64"): "x86_64-apple-darwin", ("darwin", "aarch64"): "aarch64-apple-darwin",
    ("windows", "x86_64"): "x86_64-pc-windows-msvc",
}


def tectonic_asset_pattern(system: str | None = None, machine: str | None = None) -> str | None:
    """The regular expression of Tectonic's release file for this machine (`tectonic-0.17.0-aarch64-apple-darwin.tar.gz`)."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    target = TECTONIC_TARGETS.get((system, machine))
    if target is None:
        return None
    return r"tectonic-[\d.]+-" + re.escape(target) + (r"\.zip" if system == "windows" else r"\.tar\.gz")


def install_tectonic(fetch=None, release: dict | None = None) -> bool:
    """Download Tectonic's release binary for this machine into tools_directory()."""
    pattern = tectonic_asset_pattern()
    if pattern is None:
        print(f"No Tectonic release is listed for {platform.system()} {platform.machine()}; "
              f"see https://github.com/{TECTONIC_REPOSITORY}/releases", file=sys.stderr)
        return False
    asset = release_asset_matching(TECTONIC_REPOSITORY, pattern, release)
    if asset is None:
        print("GitHub lists no Tectonic download for this machine with a SHA-256 (offline, or a rate limit?), so none is made "
              "unchecked. Install it with your package manager (brew install tectonic) or from tectonic-typesetting.github.io.",
              file=sys.stderr)
        return False
    name, url, sha256 = asset
    print(f"INSTALL  tectonic (10 to 22 MB download): {url}")
    executable = "tectonic.exe" if name.endswith(".zip") else "tectonic"
    with NamedTemporaryFile(suffix=".zip" if name.endswith(".zip") else ".tar.gz", delete=False) as temporary:
        archive = Path(temporary.name)
    try:
        (fetch or core.download_file)(url, archive, sha256)
        print(f"SHA-256 verified ({sha256[:12]}..., as listed by GitHub for this release)")
        target = extract_executable(archive, executable, core.tools_directory())
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"Could not install Tectonic ({error}). Install it yourself: brew install tectonic | "
              "tectonic-typesetting.github.io", file=sys.stderr)
        return False
    finally:
        archive.unlink(missing_ok=True)
    core.use_managed_tools()
    ran = core.run_probe([str(target), "--version"])
    if ran is None or ran.returncode != 0:
        print(f"Tectonic was downloaded to {target} but does not run here: {ran.stderr.strip() if ran else 'it does not answer'}", file=sys.stderr)
        return False
    print(f"Installed {ran.stdout.strip()} in {core.tools_directory()} (used when no other Tectonic is on PATH; delete the file to "
          "remove it). It fetches the TeX files a document needs from the network the first time (about 100 MB over time), "
          "then works from its cache.")
    return True


def install_kind(value: str) -> str:
    """argparse type of --install: a kind, or `fonts:NAME[,NAME...]` / `ocr:LANG[,LANG...]` / `math:katex` / `diagram:d2|dot`."""
    kind = value.partition(":")[0]
    if (kind not in core.INSTALL_KINDS or (":" in value and kind not in ("fonts", "ocr", "math", "diagram", "core", "kit"))
            or (kind == "core" and ":" in value and value not in ("core:tex", "core:typst"))
            or (kind == "math" and ":" in value and value not in ("math:katex", "math:mathjax"))
            or (kind == "diagram" and ":" in value and value.partition(":")[2] not in DIAGRAM_INSTALLS)):
        raise argparse.ArgumentTypeError(f"invalid choice: {value!r} (choose from {', '.join(core.INSTALL_KINDS)}; "
                                         "fonts takes names: fonts:arabic,cjk-sc; ocr takes languages: ocr:rus,kaz; "
                                         "math:mathjax is MathJax and math:katex is KaTeX, for math in WeasyPrint's PDFs; diagram:d2 and "
                                         "diagram:dot draw ```d2 and ```dot blocks; core:tex is Pandoc and Tectonic, core:typst Pandoc and Typst; "
                                         "kit:SOURCE installs the kits of a repository: kit:owner/repo, kit:owner/repo@v1#name, kit:apa7)")
    return value


def uninstall_kind(value: str) -> str:
    if value.partition(":")[0] not in ("fonts", "ocr", "kit") or (value.startswith("kit") and not value.partition(":")[2]):
        raise argparse.ArgumentTypeError("only fonts, OCR languages and kits that pdfmd installed can be uninstalled: "
                                         "--uninstall fonts:NAME[,NAME...], ocr:LANG[,LANG...] or kit:NAME")
    return value


KIT_SOURCES_DEFAULT = ["aliperdehan/pdfmd-kits"]       # where a bare name (`--install kit:apa7`) is looked for: `kit-sources` of the config


def kit_install_settings() -> dict:
    """The install-time settings, from `options:` of the config file (they are not per document): `kit-search-depth` (levels below
    a repository's root that are searched for kits, 3), `kit-install-max-mb` (200), `kit-install-max-files` (5000) and
    `kit-sources` (the repositories a bare kit name is looked for in, a list of `owner/repo` or URLs)."""
    options = core.config_options()

    def number(key: str, default: int) -> int:
        value = options.get(key, default)
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            print(f"WARN  config: {key} must be a whole number (got {value!r}); using {default}", file=sys.stderr)
            return default

    sources = options.get("kit-sources", KIT_SOURCES_DEFAULT)
    sources = [str(item) for item in sources] if isinstance(sources, (list, tuple)) else [str(sources)]
    return {"depth": number("kit-search-depth", 3), "max_bytes": number("kit-install-max-mb", 200) * 1048576,
            "max_files": number("kit-install-max-files", 5000), "sources": sources}


def install_kits(value: str, assume_yes: bool = False) -> bool:
    """`pdfmd --install kit[:SOURCE]`: the kits of a repository (see pdfmd_kits/install.py), or the list of the installed ones."""
    from pdfmd_kits import install as kit_installer
    target = core.kits_install_directory()
    if target is None:
        print("ERROR  PDFMD_CONFIG is empty: there is no config folder to install kits beside", file=sys.stderr)
        return False
    if not value.strip():
        installed = kit_installer.installed_kits(target)
        if not installed:
            print("No kit installed by pdfmd. Install the kits of a repository: pdfmd --install kit:owner/repo "
                  "(or kit:apa7 for a kit of the repositories in `kit-sources`)")
        for folder, record in installed:
            where = record.get("source", "?") + (f"@{record['ref']}" if record.get("ref") else "")
            commit = f" {record['commit'][:10]}" if record.get("commit") else ""
            print(f"{record.get('kit', folder.name)} {record.get('version', '')}".rstrip().ljust(24) + f"  {where}{commit}  {core.display_path(folder)}")
        return True
    settings = kit_install_settings()
    try:
        source = kit_installer.parse_source(value)
        attempts = [source]
        if source.kind == "name":
            import dataclasses
            attempts = [dataclasses.replace(kit_installer.parse_source(item), name=source.location) for item in settings["sources"]]
            if not attempts:
                raise kit_installer.InstallError(f"{value!r} is a kit's name, and `kit-sources` in the config names no repository: "
                                                 "pdfmd --install kit:owner/repo")
        problems: list[str] = []
        for attempt in attempts:
            try:
                done = kit_installer.install(attempt, target, depth=settings["depth"], max_bytes=settings["max_bytes"],
                                             max_files=settings["max_files"], download=core.download_file, assume_yes=assume_yes,
                                             say=lambda text: print(text), run=subprocess.run)
            except kit_installer.InstallError as error:
                if len(attempts) == 1:
                    raise
                problems.append(f"{attempt.location}: {error}")
                continue
            for item in done:
                modes = ", ".join(item.modes)
                print(f"INSTALLED  {item.name} {item.version}".rstrip() + f"  {core.display_path(item.folder)}"
                      + ("  (replaced the one installed before)" if item.replaced else "") + (f"\n           modes: {modes}" if modes else ""))
                for warning in item.warnings:
                    print(f"WARN  {warning}", file=sys.stderr)
            code = [item for item in done if item.lua]
            if code:
                print("NOTE  " + ", ".join(f"{item.name} ({', '.join(item.lua)})" for item in code) + " ships a Lua filter: pdfmd "
                      "runs it, and a Lua filter can run any command, so read it (pdfmd --kits NAME shows where it is) before you "
                      "use a kit from a source you do not know. Choose a kit with --kit NAME[:MODE].")
            return True
        raise kit_installer.InstallError(f"no kit {value!r} in the repositories of `kit-sources`: " + "; ".join(problems))
    except kit_installer.InstallError as error:
        print(f"ERROR  {error}", file=sys.stderr)
        return False


def install_fonts(names: str) -> bool:
    """`pdfmd --install fonts[:NAME,NAME...]`: list the catalog, or fetch fonts into
    pdfmd's own folder (see pdfmd_unicode/install.py)."""
    module = core.unicode_module()
    if module is None:
        print("The fonts installer is part of the pdfmd_unicode package, which is not installed beside "
              "this file (pip install pdfmd-cli).", file=sys.stderr)
        return False
    from pdfmd_unicode import install as installer
    if not names.strip():
        print(installer.table(core.fonts_directory()))
        return True
    try:
        keys = installer.resolve(names.split(","))
    except installer.UnknownPackage as error:
        print(f"No font package or group called {error.args[0]!r}. `pdfmd --install fonts` lists them.",
              file=sys.stderr)
        return False
    failed = installer.install(keys, core.fonts_directory())
    core.reset_font_caches()
    done = [key for key in keys if key not in failed]
    if done:
        print(f"Installed {', '.join(done)} in {core.fonts_directory()}; pdfmd uses them from now on "
              "(delete the folder, or `pdfmd --uninstall fonts:NAME`, to remove).")
    return not failed


def install_extra(kind: str, assume_yes: bool = False) -> bool:
    """Install an optional piece: pip packages into the Python environment pdfmd runs
    from (math, emoji, pandoc), or Typst's own binary into pdfmd's tools folder."""
    if kind == "kit" or kind.startswith("kit:"):
        return install_kits(kind.partition(":")[2], assume_yes)
    if kind == "full":
        return core.install_extra("pandoc") and core.install_extra("typst")
    if kind == "typst":
        return core.install_typst()
    if kind in ("core", "core:typst"):
        return core.install_extra("full")
    if kind in ("core:tex", "cortex"):
        return core.install_extra("pandoc") and core.install_tectonic()
    if kind == "math:katex":
        return install_katex()
    if kind == "math:mathjax":
        return install_mathjax()
    if kind == "calibre":
        return install_calibre()
    if kind == "diagram" or kind.startswith("diagram:"):
        return install_diagram(kind.partition(":")[2])
    if kind == "ocr" or kind.startswith("ocr:"):
        return core.install_ocr_languages(kind.partition(":")[2])
    if kind == "emoji" or kind == "fonts" or kind.startswith("fonts:"):
        return install_fonts("emoji" if kind == "emoji" else kind.partition(":")[2])
    if kind == "math" and sys.version_info < (3, 11):
        print("pymd2pdf needs Python 3.11 or newer; this is "
              f"{sys.version.split()[0]}. Install pdfmd with a newer Python (pipx install pdfmd-cli).",
              file=sys.stderr)
        return False
    if kind == "batchocr":
        print("NOTE  PyMuPDF (AGPL-3.0) is installed by batchocr as its own package; pdfmd does not bundle it")
        specs = [core.batchocr_spec()]
    else:
        specs = INSTALL_SPECS[kind]
    command = [sys.executable, "-m", "pip", "install", *specs]
    print(f"INSTALL  {kind} ({core.INSTALL_SIZES[kind]}): " + " ".join(shlex.quote(part) for part in command))
    try:
        completed = subprocess.run(command, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode != 0 and "externally-managed-environment" in (completed.stderr or ""):
            # PEP 668 (Homebrew's or Debian's Python): not the system's packages, pdfmd's own folder (v3.28.26)
            folder = core.own_python_folder()
            command = [sys.executable, "-m", "pip", "install", "--upgrade", "--target", str(folder), *specs]
            print(f"NOTE  this Python is managed by the system (PEP 668); installing into pdfmd's own folder {core.display_path(folder)}: "
                  + " ".join(shlex.quote(part) for part in command))
            folder.mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(command)
            if completed.returncode == 0 and str(folder) not in sys.path:
                sys.path.append(str(folder))
                importlib.invalidate_caches()
    except OSError as error:
        print(f"Could not run pip ({error}).", file=sys.stderr)
        return False
    if completed.returncode != 0:
        print(f'pip failed. Install by hand: pip install "pdfmd-cli[{kind}]"', file=sys.stderr)
        return False
    if kind == "batchocr":
        importlib.invalidate_caches()
        found = core.find_batchocr()
        version = core.batchocr_version(found) if found else None
        print(f"Installed batchocr {'.'.join(map(str, version)) if version else '(not found yet)'}.")
        core.install_ocr_tools()
    if kind == "tui":
        print("Installed prompt_toolkit. `pdfmd --setup fancy` opens the full-screen setup; to make it the default, "
              "set \"This setup screen\" to fancy there.")
    if kind == "pandoc":
        importlib.invalidate_caches()
        core.use_managed_tools()
        found = core.which("pandoc")
        print(f"Installed Pandoc ({found or 'not found on PATH yet'}); "
              "used when no other Pandoc is on PATH.")
    return True
