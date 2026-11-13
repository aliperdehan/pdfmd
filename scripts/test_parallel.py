#!/usr/bin/env python3
"""Run pdfmd's test modules in parallel worker processes (unittest has no parallel mode of its own).

    python3 scripts/test_parallel.py [-j N] [--failed-only] [--keep] [--quiet] [PATTERN ...]

Each module of tests/ runs as `python3 -m unittest discover -s tests -p test_x.py` from the repository root, the way a serial
discovery would load it, in one of N worker processes (`-j`, default: the number of CPUs). PATTERN is a module name (`test_tables`),
a file name, or a shell pattern (`'test_kit_*'`); without one, every tests/test_*.py runs.

Every worker has folders of its own, all under one temporary folder that is removed at the end (`--keep` leaves it): XDG_CONFIG_HOME,
XDG_CACHE_HOME, XDG_DATA_HOME, TMPDIR and, with
`--own-tex-cache`, TEXMFVAR (a fresh one makes luaotfload rebuild its font database, minutes per worker, so it is off by default).
PDFMD_CONFIG is empty, PDFMD_NO_PROMPT=1, stdin is /dev/null. The real cache, config and data folders of pdfmd are compared
before and after the run, and the runner says whether anything in them changed.

Slowest modules start first: the duration of each is kept in a timings file under the system temporary folder (not in the repository
or in pdfmd's cache); a module without a timing counts by its file size. The modules in SERIAL run alone, after the parallel phase.
`--failed-only` runs again the modules that failed last time. Exit status 1 when any module failed.
"""

from __future__ import annotations

import argparse
import fnmatch
import itertools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
STATE = Path(tempfile.gettempdir()) / f"pdfmd-test-parallel-{os.getuid() if hasattr(os, 'getuid') else 'user'}.json"

# Modules (or shell patterns) that must not run beside another one, each with its reason; they run one at a time after the
# parallel phase, when nothing else is running.
SERIAL: dict[str, str] = {
    "test_colophon_*": "each compiles Swift (swiftc, a 120 s limit inside the test), which times out beside the LaTeX builds of the "
                       "workers: the whole group runs one module at a time after the parallel phase, when nothing else runs",
}

# Modules that need the environment the runner was started in, not a worker's: they run alone, in the serial phase, and guard the
# real folders themselves.
OWN_ENVIRONMENT: dict[str, str] = {
    "test_isolation": "it checks that the run watches the real cache, config and data folders, which a worker's variables hide",
}


CHILDREN: set = set()                  # the worker processes running now
CHILDREN_LOCK = threading.Lock()


STOPPED = threading.Event()            # set when the run is interrupted: queued modules are not started


def stop_children() -> None:
    """End workers and their descendants, including tools in separate sessions."""
    STOPPED.set()
    with CHILDREN_LOCK:
        running = [child for child in CHILDREN if child.poll() is None]
    if os.name == "nt":
        for child in running:
            try:
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except OSError:
                pass
    else:
        try:
            listing = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True).stdout
            descendants: dict[int, list[int]] = {}
            for line in listing.splitlines():
                try:
                    pid, parent = map(int, line.split())
                except ValueError:
                    continue
                descendants.setdefault(parent, []).append(pid)
            pending = [child.pid for child in running]
            found = []
            while pending:
                pid = pending.pop()
                for descendant in descendants.get(pid, []):
                    found.append(descendant)
                    pending.append(descendant)
            for pid in reversed(found):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        except (OSError, subprocess.CalledProcessError):
            pass
    for child in running:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except (OSError, AttributeError):
            try:
                child.kill()
            except OSError:
                pass


def _terminate(signum, frame) -> None:
    stop_children()
    raise KeyboardInterrupt


def modules(patterns: list[str]) -> list[str]:
    """The module names (`test_x`) the patterns select, in name order; no pattern selects every tests/test_*.py."""
    every = sorted(path.stem for path in TESTS.glob("test_*.py"))
    if not patterns:
        return every
    chosen: list[str] = []
    for pattern in patterns:
        name = pattern.rsplit("/", 1)[-1]
        name = name[:-3] if name.endswith(".py") else name
        found = [m for m in every if fnmatch.fnmatchcase(m, name)] or [m for m in every if name in m and not any(c in name for c in "*?[")]
        if not found:
            sys.exit(f"test_parallel: no test module matches {pattern!r}")
        chosen += [m for m in found if m not in chosen]
    return chosen


def schedule(names: list[str], timings: dict[str, float], serial: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    """(parallel, serial): the parallel modules slowest first (a module with no timing counts by file size, as a guess in seconds
    scaled to be below any measured one that is slow, above the ones that are fast), then the serial ones, which run alone."""
    serial = {**SERIAL, **OWN_ENVIRONMENT} if serial is None else serial

    def size(name: str) -> float:
        try:
            return (TESTS / f"{name}.py").stat().st_size / 20000.0   # a 20 kB module guesses at 1 s: only an order
        except OSError:
            return 0.0

    def cost(name: str) -> float:
        return timings.get(name, size(name))

    def alone(name: str) -> bool:
        return any(fnmatch.fnmatchcase(name, pattern) for pattern in serial)

    ordered = sorted(names, key=lambda n: (-cost(n), n))
    return [n for n in ordered if not alone(n)], [n for n in ordered if alone(n)]


def parse(output: str) -> dict[str, int]:
    """The counts unittest prints at the end of a run (`Ran 3 tests`, `FAILED (failures=1, errors=2, skipped=1)`)."""
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    ran = re.findall(r"^Ran (\d+) tests? in ", output, re.M)
    if ran:
        counts["tests"] = int(ran[-1])
    tail = re.findall(r"^(?:OK|FAILED) \((.*)\)\s*$", output, re.M)
    for key, number in re.findall(r"(failures|errors|skipped)=(\d+)", tail[-1] if tail else ""):
        counts[key] = int(number)
    return counts


def worker_env(base: Path, slot: str, own_tex: bool, name: str = "") -> dict[str, str]:
    """The environment of one worker: folders of its own under `base`, no config, no prompts (a module in OWN_ENVIRONMENT gets
    the runner's own environment unchanged, but for the prompts)."""
    if name in OWN_ENVIRONMENT:
        return {k: v for k, v in os.environ.items() if k != "PDFMD_TESTS_SCRATCH"} | {"PDFMD_NO_PROMPT": "1"}
    home = base / slot
    env = dict(os.environ)
    for name in ("config", "cache", "data", "tmp"):
        (home / name).mkdir(parents=True, exist_ok=True)
    env.update({"XDG_CONFIG_HOME": str(home / "config"), "XDG_CACHE_HOME": str(home / "cache"), "XDG_DATA_HOME": str(home / "data"),
                "TMPDIR": str(home / "tmp"), "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
    if own_tex:
        (home / "texmf-var").mkdir(exist_ok=True)
        env["TEXMFVAR"] = str(home / "texmf-var")
    return env


def run_module(name: str, env: dict[str, str]) -> dict:
    """Run one module alone; its counts, status, duration and output."""
    start = time.monotonic()
    if STOPPED.is_set():
        return {"name": name, "status": "FAIL", "seconds": 0.0, "output": "not run: interrupted", "code": 1, "tests": 0,
                "failures": 0, "errors": 0, "skipped": 0}
    try:
        # A session of its own: the whole process group (LaTeX, Pandoc, ...) can be ended when the runner is stopped.
        with CHILDREN_LOCK:
            if STOPPED.is_set():
                return {"name": name, "status": "FAIL", "seconds": 0.0, "output": "not run: interrupted", "code": 1, "tests": 0,
                        "failures": 0, "errors": 0, "skipped": 0}
            child = subprocess.Popen([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", f"{name}.py"], cwd=ROOT, env=env,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     errors="replace", start_new_session=True)
            CHILDREN.add(child)
        try:
            output = child.communicate()[0]
        finally:
            with CHILDREN_LOCK:
                CHILDREN.discard(child)
        code = child.returncode
    except OSError as error:
        output, code = f"could not start: {error}", 1
    counts = parse(output)
    empty = counts["tests"] == 0 and code == 5 and re.search(r"^Ran 0 tests in ", output, re.M)   # a helper module such as test_00_environment
    bad = (code != 0 and not empty) or counts["failures"] or counts["errors"] or (counts["tests"] == 0 and not empty)
    return {"name": name, "status": "FAIL" if bad else "ok", "seconds": time.monotonic() - start, "output": output, "code": code, **counts}


def real_folders() -> list[Path]:
    """pdfmd's real cache, config and data folders as the runner's own environment names them. Asked of a child process: importing
    tests/isolation_support redirects the importer's own XDG variables to a scratch folder and registers a check at exit, which the
    runner (and the workers that inherit its environment) must not have."""
    code = "import json, isolation_support as i; print(json.dumps([str(p) for p in i.REAL]))"
    done = subprocess.run([sys.executable, "-c", code], cwd=TESTS, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          check=False, env={k: v for k, v in os.environ.items() if k != "PDFMD_TESTS_SCRATCH"})
    try:
        return [Path(p) for p in json.loads(done.stdout.strip().splitlines()[-1])]
    except (ValueError, IndexError):
        sys.exit(f"test_parallel: cannot find pdfmd's real folders: {done.stderr.strip()}")


def snapshot(folders: list[Path]) -> dict[str, tuple[int, int]]:
    """Every file and folder under the folders (path -> mtime, size)."""
    seen: dict[str, tuple[int, int]] = {}
    for folder in folders:
        for where, dirs, files in os.walk(folder):
            for entry in dirs + files:
                path = os.path.join(where, entry)
                try:
                    info = os.lstat(path)
                except OSError:
                    continue
                seen[path] = (info.st_mtime_ns, info.st_size)
    return seen


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run pdfmd's test modules in parallel.")
    ap.add_argument("patterns", nargs="*", help="module names, file names or shell patterns (default: all of tests/test_*.py)")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1, help="worker processes (default: the number of CPUs)")
    ap.add_argument("--failed-only", action="store_true", help="run only the modules that failed in the last run")
    ap.add_argument("--own-tex-cache", action="store_true", help="give each worker its own TEXMFVAR (slow: fonts are indexed again)")
    ap.add_argument("--keep", action="store_true", help="keep the temporary folder of the workers")
    ap.add_argument("--quiet", action="store_true", help="print only failures and the totals")
    args = ap.parse_args(argv)
    if args.jobs < 1:
        ap.error("-j must be at least 1")

    state = load_state()
    names = modules(args.patterns)
    if args.failed_only:
        names = [n for n in names if n in state.get("failed", [])]
        if not names:
            print("no module failed last time")
            return 0
    parallel, serial = schedule(names, state.get("timings", {}))

    watched = real_folders()
    before = snapshot(watched)
    base = Path(tempfile.mkdtemp(prefix="pdfmd-tests-"))
    results: list[dict] = []
    lock = threading.Lock()
    width = max(len(n) for n in names)
    start = time.monotonic()

    def report(result: dict) -> None:
        with lock:
            results.append(result)
            if not args.quiet or result["status"] != "ok":
                print(f"{result['status']:4}  {result['name']:{width}}  {result['tests']:5} tests  {result['skipped']:3} skipped  {result['seconds']:7.1f} s"
                      f"  [{len(results)}/{len(names)}]", flush=True)

    slots: list[str] = []
    slot_lock = threading.Lock()
    counter = itertools.count()

    def job(name: str) -> None:
        if STOPPED.is_set():
            return
        with slot_lock:
            slot = slots.pop() if slots else f"w{next(counter)}"
        try:
            report(run_module(name, worker_env(base, slot, args.own_tex_cache, name)))
        finally:
            with slot_lock:
                slots.append(slot)

    for number in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):     # Windows has no SIGHUP
        if number is not None:
            signal.signal(number, _terminate)
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            try:
                list(pool.map(job, parallel))
            except KeyboardInterrupt:
                stop_children()
                raise
        for name in serial:
            report(run_module(name, worker_env(base, "serial", args.own_tex_cache, name)))
    except KeyboardInterrupt:
        stop_children()
        print("interrupted: the workers were ended", file=sys.stderr)
        return 130
    finally:
        if args.keep:
            print(f"worker folders kept: {str(base).replace(str(Path.home()), '~', 1)}")
        else:
            shutil.rmtree(base, ignore_errors=True)

    wall = time.monotonic() - start
    after = snapshot(watched)
    touched = sorted(p for p in after if before.get(p) != after[p])
    failed = sorted((r for r in results if r["status"] != "ok"), key=lambda r: r["name"])
    total = {key: sum(r[key] for r in results) for key in ("tests", "failures", "errors", "skipped")}

    for r in failed:
        print(f"\n{'=' * 70}\nFAILED MODULE {r['name']} (exit {r['code']}, {r['tests']} tests)\n{'=' * 70}\n{r['output'].rstrip()}")
    print(f"\n{total['tests']} tests in {len(results)} modules: {total['failures']} failures, {total['errors']} errors, "
          f"{total['skipped']} skipped; {len(failed)} modules failed; wall time {wall:.1f} s with -j {args.jobs}")
    if touched:
        home = str(Path.home())
        print(f"WARNING: {len(touched)} paths in pdfmd's real cache/config/data folders changed during the run:")
        for path in touched[:20]:
            print("  " + path.replace(home, "~", 1))
    else:
        print("pdfmd's real cache, config and data folders were not changed")

    timings = state.get("timings", {})
    timings.update({r["name"]: round(r["seconds"], 2) for r in results if r["tests"]})
    old_failed = set(state.get("failed", []))
    ran = {r["name"] for r in results}
    state["timings"] = timings
    state["failed"] = sorted((old_failed - ran) | {r["name"] for r in failed})
    save_state(state)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
