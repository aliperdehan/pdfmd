"""Installing kits from a repository: `pdfmd --install kit:SOURCE`.

SOURCE is where the kits are, whoever published them:

    owner/repo                 a GitHub repository (its default branch)
    owner/repo@v1.2            a tag, a branch or a commit
    owner/repo#apa7            only the kit called apa7 of that repository (a name, as `--kit` takes it)
    https://host/path.git      any git URL (https, ssh, scp-like `git@host:path`); `@REF` and `#NAME` work the same
    ./folder  ~/kits  /x/y     a folder on this machine (copied as it is, uncommitted changes included)
    file:///x/y                a local git repository (its committed state; @REF works)
    apa7                       no slash: the kit of that name in the repositories of `kit-sources` (see sources())

The repository is fetched as a snapshot (GitHub: its tarball over https, no git needed; any other URL: `git clone --depth 1`
with only the https, ssh and file transports), unpacked in a temporary folder, and searched for kits: a folder that holds `.kit`
or `NAME.kit` is a kit, the repository root first, then every folder below it up to `depth` levels, and a kit's own
sub-folders are the kit's, never searched. So a repository that is one kit (a `.kit` in its root) and one that holds a kit per
folder both work. Every kit found is checked with the kit loader and copied whole to `KITS/NAME/`, the folder beside the config
file that kit discovery already reads, with `.pdfmd-install.json` beside it saying where it came from.

Nothing is run: not a script of the repository, not a hook, not a kit's Lua filter. The archive is read as data: no name may
leave the folder, no link, device or special file is kept, and the number of files and bytes is capped (the caller gives the
caps; they are settings). This module imports nothing from pdfmd: the caller hands in the downloader.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from pdfmd_assemble.paths import confined_destination

from .kitfile import FILE, SUFFIX, Kit, KitError, load_kit, normalise

RECORD = ".pdfmd-install.json"
RECORD_FORMAT = 1
GIT_PROTOCOLS = "https:ssh:file"                       # what `git clone` may use: no ext::, no plain git://


class InstallError(Exception):
    """Something that stops the install, said in a sentence."""


@dataclass(frozen=True)
class Source:
    text: str                     # as given
    kind: str                     # "github" | "git" | "folder" | "name"
    location: str                 # owner/repo, a URL or a path; for "name" the kit name
    ref: str = ""                 # "" = the default branch
    name: str = ""                # "" = every kit found


@dataclass
class Fetched:
    root: Path                    # the unpacked repository
    commit: str = ""
    archive_sha256: str = ""


@dataclass
class Installed:
    name: str
    folder: Path
    version: str
    source: str
    ref: str
    commit: str
    replaced: bool = False
    modes: tuple[str, ...] = ()
    lua: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


_SHORT = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GITHUB = re.compile(r"^https://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:/tree/([^#]+?))?/?$")


def parse_source(text: str) -> Source:
    """Read the SOURCE of `--install kit:SOURCE`; raises InstallError for what cannot be a source."""
    raw = text.strip()
    if not raw:
        raise InstallError("name a repository (owner/repo), a git URL, a folder or the name of a kit: pdfmd --install kit:owner/repo")
    name = ""
    if "#" in raw:
        raw, _, name = raw.rpartition("#")
        name = name.strip()
        if not name:
            raise InstallError(f"{text!r}: nothing after # (the name of a kit)")
    ref = ""
    last = max(raw.rfind("/"), raw.rfind(":"))
    at = raw.rfind("@")
    if at > last and at > 0:                           # `owner/repo@v1`, not the `git@` of `git@host:o/r.git`
        raw, ref = raw[:at], raw[at + 1:]
        if not ref:
            raise InstallError(f"{text!r}: nothing after @ (a tag, a branch or a commit)")
    if raw.lower().startswith(("http://", "git://")):
        raise InstallError(f"{text!r}: plain http and git:// carry the kits unprotected; use https (or ssh)")
    if raw.startswith(("./", "../", "/", "~")) or re.match(r"^[A-Za-z]:[\\/]", raw):
        if ref:
            raise InstallError(f"{text!r}: a folder has no @ref (give a git repository's URL, file:///path for a local one)")
        return Source(text, "folder", raw, "", name)
    github = _GITHUB.match(raw)
    if github:
        return Source(text, "github", f"{github.group(1)}/{github.group(2)}", ref or (github.group(3) or ""), name)
    if _SHORT.match(raw):
        return Source(text, "github", raw[:-4] if raw.endswith(".git") else raw, ref, name)
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw) or re.match(r"^[\w.-]+@[\w.-]+:", raw):
        return Source(text, "git", raw, ref, name)
    if "/" not in raw and ":" not in raw:
        if ref:
            raise InstallError(f"{text!r}: a kit's name takes no @ref here; say the repository: owner/repo@ref#name")
        return Source(text, "name", raw, "", "")
    raise InstallError(f"{text!r} is not a repository (owner/repo), a git URL, a folder (./x, ~/x) or a kit's name")


def safe_extract(archive: Path, destination: Path, max_bytes: int, max_files: int) -> Path:
    """Unpack a .tar.gz into ``destination`` and return the folder that holds the repository (its single top folder, which
    GitHub's tarballs have). Refuses a name that leaves ``destination``, keeps only files and folders (a link, device or
    fifo is skipped with no trace), and stops over ``max_files`` files or ``max_bytes`` bytes in all."""
    destination.mkdir(parents=True, exist_ok=True)
    total = count = 0
    written: list[str] = []
    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle:
            name = member.name
            parts = PurePosixPath(name).parts
            if member.name == "pax_global_header" or not parts:
                continue
            try:
                target = confined_destination(destination, name)
            except (ValueError, OSError, RuntimeError):
                raise InstallError(f"the archive holds {name!r}, which leaves the folder it is unpacked in: refused") from None
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue                                # a symlink, hard link, device or fifo is not kept
            count += 1
            total += member.size
            if count > max_files:
                raise InstallError(f"the archive holds more than {max_files} files (kit-install-max-files): refused")
            if total > max_bytes:
                raise InstallError(f"the archive holds more than {max_bytes // 1048576} MB (kit-install-max-mb): refused")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = bundle.extractfile(member)
            with target.open("wb") as handle:
                shutil.copyfileobj(data, handle)
            target.chmod(0o755 if member.mode & stat.S_IXUSR else 0o644)
            written.append(parts[0])
    tops = {p.name for p in destination.iterdir()}
    if len(tops) == 1 and next(iter(tops)) == (written[0] if written else None) and (destination / next(iter(tops))).is_dir():
        return destination / next(iter(tops))
    return destination


def copy_tree(source: Path, destination: Path, max_bytes: int, max_files: int) -> None:
    """Copy ``source`` to ``destination`` without `.git` folders and without links (they are skipped), under the same caps."""
    total = count = 0
    for folder, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git" and not (Path(folder) / d).is_symlink()]
        relative = Path(folder).relative_to(source)
        (destination / relative).mkdir(parents=True, exist_ok=True)
        for item in files:
            path = Path(folder) / item
            if path.is_symlink() or not path.is_file():
                continue
            count += 1
            total += path.stat().st_size
            if count > max_files:
                raise InstallError(f"{source} holds more than {max_files} files (kit-install-max-files): refused")
            if total > max_bytes:
                raise InstallError(f"{source} holds more than {max_bytes // 1048576} MB (kit-install-max-mb): refused")
            shutil.copy2(path, destination / relative / item)


def _git(arguments: list[str], cwd: Path | None = None, run=subprocess.run) -> str:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": GIT_PROTOCOLS}
    try:
        done = run(["git", "-c", "protocol.ext.allow=never", *arguments], cwd=cwd, env=environment, capture_output=True,
                   encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise InstallError("git is not installed: use owner/repo for a GitHub repository, or install git") from None
    if done.returncode != 0:
        raise InstallError(f"git {arguments[0]} failed: {(done.stderr or done.stdout).strip().splitlines()[-1:] or ['no message']}"
                           .replace("['", "").replace("']", ""))
    return done.stdout.strip()


def fetch(source: Source, work: Path, max_bytes: int, max_files: int,
          download: Callable[[str, Path, str | None], None], run=subprocess.run) -> Fetched:
    """Bring the repository of ``source`` into ``work`` and say where its root is."""
    import hashlib
    if source.kind == "github":
        url = f"https://github.com/{source.location}/archive/{source.ref or 'HEAD'}.tar.gz"
        archive = work / "repository.tar.gz"
        try:
            download(url, archive, None)
        except OSError as error:
            raise InstallError(f"could not fetch {url}: {error}") from None
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        root = safe_extract(archive, work / "repository", max_bytes, max_files)
        top = root.name
        commit = top.rsplit("-", 1)[-1] if re.fullmatch(r"[0-9a-f]{40}", top.rsplit("-", 1)[-1]) else ""
        return Fetched(root, commit, digest)
    if source.kind == "git":
        target = work / "repository"
        if source.ref:
            target.mkdir()
            _git(["init", "-q"], target, run)
            _git(["fetch", "-q", "--depth", "1", "--no-tags", source.location, source.ref], target, run)
            _git(["checkout", "-q", "FETCH_HEAD"], target, run)
        else:
            _git(["clone", "-q", "--depth", "1", "--no-tags", source.location, str(target)], None, run)
        commit = _git(["rev-parse", "HEAD"], target, run)
        _count(target, max_bytes, max_files)
        return Fetched(target, commit)
    if source.kind == "folder":
        origin = Path(os.path.expanduser(source.location))
        if not origin.is_dir():
            raise InstallError(f"{source.location} is not a folder")
        target = work / "repository"
        copy_tree(origin, target, max_bytes, max_files)
        return Fetched(target, "")
    raise InstallError(f"{source.text!r} has to be resolved to a repository first")


def _count(folder: Path, max_bytes: int, max_files: int) -> None:
    total = count = 0
    for item in folder.rglob("*"):
        if ".git" in item.relative_to(folder).parts[:1]:
            continue
        if item.is_file() and not item.is_symlink():
            count += 1
            total += item.stat().st_size
    if count > max_files:
        raise InstallError(f"the repository holds more than {max_files} files (kit-install-max-files): refused")
    if total > max_bytes:
        raise InstallError(f"the repository holds more than {max_bytes // 1048576} MB (kit-install-max-mb): refused")


def find_kits(root: Path, depth: int) -> list[Path]:
    """The `.kit` files of a repository: the root's, or else those of its folders down to ``depth`` levels (hidden folders are
    not looked into). A folder that is a kit is not searched further: what is below it belongs to it."""
    found: list[Path] = []

    def visit(folder: Path, level: int) -> None:
        own = [folder / FILE] if (folder / FILE).is_file() else sorted(
            item for item in folder.glob(f"*{SUFFIX}") if item.is_file() and item.stem and not item.name.startswith("."))
        if own:
            found.extend(own)
            return
        if level >= depth:
            return
        for child in sorted(folder.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and not child.is_symlink():
                visit(child, level + 1)

    visit(root, 0)
    return found


def _safe_folder_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip(".-")
    if not cleaned:
        raise InstallError(f"a kit's name ({name!r}) cannot be a folder name")
    return cleaned


def read_record(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def installed_kits(kits_dir: Path) -> list[tuple[Path, dict]]:
    """The kits pdfmd installed (folders of ``kits_dir`` with a record), by folder name."""
    if not kits_dir.is_dir():
        return []
    found = [(folder, read_record(folder)) for folder in sorted(kits_dir.iterdir()) if folder.is_dir()]
    return [(folder, record) for folder, record in found if record]


def uninstall(name: str, kits_dir: Path) -> Path:
    """Remove the kit called ``name`` that pdfmd installed; a kit it did not install is never touched."""
    wanted = normalise(name)
    for folder, record in installed_kits(kits_dir):
        if normalise(folder.name) == wanted or normalise(record.get("kit", "")) == wanted:
            shutil.rmtree(folder)
            return folder
    raise InstallError(f"no kit called {name!r} was installed by pdfmd in {kits_dir} (a kit you put there yourself is not touched)")


def install(source: Source, kits_dir: Path, *, depth: int, max_bytes: int, max_files: int,
            download: Callable[[str, Path, str | None], None], assume_yes: bool = False,
            say: Callable[[str], None] = print, run=subprocess.run, workdir: Path | None = None) -> list[Installed]:
    """Fetch ``source`` and install the kits it holds into ``kits_dir``. Returns what was installed."""
    if source.kind == "name":
        raise InstallError("resolve a bare kit name to a repository before installing")
    with tempfile.TemporaryDirectory(prefix="pdfmd-kit-", dir=workdir) as temporary:
        work = Path(temporary)
        say(f"INSTALL  kits from {source.text} ...")
        fetched = fetch(source, work, max_bytes, max_files, download, run)
        files = find_kits(fetched.root, depth)
        if not files:
            raise InstallError(f"{source.text}: no kit found (a kit is a folder with a `.kit` or `NAME.kit` file; looked in the "
                               f"repository's root and in its folders down to {depth} level(s))")
        kits: list[Kit] = []
        skipped: list[str] = []
        for path in files:
            try:
                kits.append(load_kit(path))
            except KitError as error:
                skipped.append(f"{path.relative_to(fetched.root)}: {error.problems[0]}")
        for message in skipped:
            say(f"WARN  skipped, not a valid kit: {message}")
        if source.name:
            wanted = normalise(source.name)
            kits = [kit for kit in kits if kit.answers_to(source.name) or normalise(kit.folder.name) == wanted]
            if not kits:
                raise InstallError(f"{source.text}: the repository has no kit called {source.name!r}")
        if not kits:
            raise InstallError(f"{source.text}: every `.kit` file in it has faults (above)")
        folders = [kit.folder for kit in kits]
        if len(set(folders)) != len(folders):
            raise InstallError(f"{source.text}: two `.kit` files share one folder; a kit is a folder")
        kits_dir.mkdir(parents=True, exist_ok=True)
        done: list[Installed] = []
        for kit in kits:
            target = kits_dir / _safe_folder_name(kit.name)
            existing = read_record(target) if target.exists() else None
            replaced = False
            if target.exists():
                if existing is None:
                    raise InstallError(f"{target} exists and was not installed by pdfmd: move it away or name another kit")
                if existing.get("source") != source.location and not assume_yes:
                    raise InstallError(f"{target} is the kit {kit.name!r} from {existing.get('source')}; this one is from "
                                       f"{source.location}. Add --yes to replace it")
                replaced = True
            staging = kits_dir / f".{target.name}.new"
            if staging.exists():
                shutil.rmtree(staging)
            copy_tree(kit.folder, staging, max_bytes, max_files)
            record = {"format": RECORD_FORMAT, "kit": kit.name, "version": kit.version, "source": source.location,
                      "kind": source.kind, "ref": source.ref, "commit": fetched.commit,
                      "archive-sha256": fetched.archive_sha256,
                      "path-in-repository": kit.folder.relative_to(fetched.root).as_posix().replace(".", "", 1) if kit.folder == fetched.root else kit.folder.relative_to(fetched.root).as_posix(),
                      "installed": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            (staging / RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            old = kits_dir / f".{target.name}.old"
            if replaced:
                if old.exists():
                    shutil.rmtree(old)
                target.rename(old)
            staging.rename(target)
            if replaced:
                shutil.rmtree(old)
            done.append(Installed(kit.name, target, kit.version, source.location, source.ref, fetched.commit, replaced,
                                  tuple(kit.modes), tuple(path.name for path in kit.lua), tuple(kit.warnings)))
        return done
