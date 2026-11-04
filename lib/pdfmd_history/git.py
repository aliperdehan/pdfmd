"""What a document's history needs from git, when it is in a repository (the repository may be a folder or three above
the document): its commits, a file as it was at one, and where it stands now. Every function says "no" quietly --
None or an empty list -- when git is missing, the file is not tracked, or anything else goes wrong."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Commit:
    full: str
    short: str
    when: float                  # seconds since the epoch
    author: str
    subject: str


def _git(folder: Path, *arguments: str, timeout: int = 20) -> subprocess.CompletedProcess | None:
    executable = shutil.which("git")
    if executable is None:
        return None
    try:
        return subprocess.run([executable, "-C", str(folder), *arguments], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def tracked_name(path: Path) -> str | None:
    """The path of `path` as git knows it (relative to the repository), or None when it is not in a repository or git
    does not track it."""
    done = _git(path.parent, "ls-files", "--full-name", "--error-unmatch", "--", path.name)
    if done is None or done.returncode != 0 or not done.stdout.strip():
        return None
    return done.stdout.strip().splitlines()[0]


def log(path: Path, limit: int = 0) -> list[Commit]:
    """The commits that changed `path`, newest first (`limit` 0: all)."""
    if tracked_name(path) is None:
        return []
    command = ["log", "--follow", "--format=%H%x1f%h%x1f%ct%x1f%an%x1f%s"]
    if limit:
        command.append(f"-n{limit}")
    done = _git(path.parent, *command, "--", path.name)
    if done is None or done.returncode != 0:
        return []
    commits = []
    for line in done.stdout.splitlines():
        fields = line.split("\x1f")
        if len(fields) == 5:
            try:
                commits.append(Commit(fields[0], fields[1], float(fields[2]), fields[3], fields[4]))
            except ValueError:
                pass
    return commits


def show(path: Path, revision: str) -> str | None:
    """The text of `path` at `revision`."""
    name = tracked_name(path)
    if name is None:
        return None
    done = _git(path.parent, "show", f"{revision}:{name}")
    return done.stdout if done is not None and done.returncode == 0 else None


def find_commit(path: Path, prefix: str) -> Commit | None:
    """The commit of `path`'s history that `prefix` (4 or more hex digits) names, or None (also when it names several)."""
    found = [commit for commit in log(path) if commit.full.startswith(prefix.lower())]
    return found[0] if len(found) == 1 else None


def state(path: Path) -> tuple[str, bool] | None:
    """(the short hash of HEAD, whether `path` differs from it) for a tracked file, else None."""
    if tracked_name(path) is None:
        return None
    head = _git(path.parent, "rev-parse", "--short", "HEAD")
    if head is None or head.returncode != 0 or not head.stdout.strip():
        return None
    changed = _git(path.parent, "status", "--porcelain", "--", path.name)
    return head.stdout.strip(), bool(changed is not None and changed.stdout.strip())
