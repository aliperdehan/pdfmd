"""v3.33.188b: the scheduling and bookkeeping of `scripts/test_parallel.py`, without running a test module."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import test_parallel  # noqa: E402


class Schedule(unittest.TestCase):
    def test_slowest_first_and_serial_apart(self):
        parallel, serial = test_parallel.schedule(["test_a", "test_b", "test_c", "test_d"],
                                                  {"test_a": 1.0, "test_b": 50.0, "test_c": 9.0, "test_d": 99.0},
                                                  {"test_c*": "needs the whole machine"})
        self.assertEqual(parallel, ["test_d", "test_b", "test_a"])
        self.assertEqual(serial, ["test_c"])

    def test_the_colophon_group_runs_alone(self):
        parallel, serial = test_parallel.schedule(["test_colophon_alias", "test_tables", "test_colophon_x"], {})
        self.assertEqual((parallel, sorted(serial)), (["test_tables"], ["test_colophon_alias", "test_colophon_x"]))

    def test_without_timings_a_bigger_file_goes_first(self):
        names = ["test_tables", "test_00_environment"]
        sizes = {n: (ROOT / "tests" / f"{n}.py").stat().st_size for n in names}
        first = max(names, key=sizes.get)
        self.assertEqual(test_parallel.schedule(names, {}, {})[0][0], first)

    def test_serial_modules_exist(self):
        import fnmatch
        every = {path.stem for path in (ROOT / "tests").glob("test_*.py")}
        for pattern in test_parallel.SERIAL:
            self.assertTrue(fnmatch.filter(every, pattern), pattern)
        for name, reason in test_parallel.SERIAL.items():
            self.assertTrue(reason.strip(), name)


class Selection(unittest.TestCase):
    def test_patterns(self):
        self.assertEqual(test_parallel.modules(["test_tables"]), ["test_tables"])
        self.assertEqual(test_parallel.modules(["tests/test_tables.py"]), ["test_tables"])
        kits = test_parallel.modules(["test_kit_*"])
        self.assertTrue(kits and all(k.startswith("test_kit_") for k in kits))
        self.assertIn("test_tables", test_parallel.modules([]))

    def test_unknown_pattern_ends_the_run(self):
        with self.assertRaises(SystemExit):
            test_parallel.modules(["test_no_such_module_at_all"])


class Counts(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(test_parallel.parse("..\nRan 12 tests in 0.5s\n\nOK (skipped=3)\n"),
                         {"tests": 12, "failures": 0, "errors": 0, "skipped": 3})
        self.assertEqual(test_parallel.parse("Ran 1 test in 0.1s\n\nFAILED (failures=2, errors=1, skipped=4)\n"),
                         {"tests": 1, "failures": 2, "errors": 1, "skipped": 4})
        self.assertEqual(test_parallel.parse("crash")["tests"], 0)


class Environment(unittest.TestCase):
    def test_worker_folders_are_private(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            one = test_parallel.worker_env(Path(folder), "w0", False)
            two = test_parallel.worker_env(Path(folder), "w1", False)
            for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "TMPDIR"):
                self.assertNotEqual(one[key], two[key])
                self.assertTrue(one[key].startswith(folder))
            self.assertEqual((one["PDFMD_CONFIG"], one["PDFMD_NO_PROMPT"]), ("", "1"))


@unittest.skipIf(os.name == "nt", "SIGINT delivery differs on Windows")
class Interrupt(unittest.TestCase):
    def test_interrupt_stops_blocked_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "tests").mkdir()
            marker = base / "started"
            (base / "tests" / "test_blocked.py").write_text(
                "import os, time, unittest\nfrom pathlib import Path\n"
                f"class Blocked(unittest.TestCase):\n def test_wait(self):\n  Path({str(marker)!r}).write_text(str(os.getpid()))\n  time.sleep(60)\n")
            code = ("import sys; from pathlib import Path; "
                    f"sys.path.insert(0, {str(ROOT / 'scripts')!r}); import test_parallel as r; "
                    f"r.ROOT=Path({folder!r}); r.TESTS=r.ROOT/'tests'; r.STATE=r.ROOT/'state'; "
                    "r.real_folders=lambda: []; sys.exit(r.main(['-j', '1']))")
            env = {**os.environ, "TMPDIR": folder, "XDG_CONFIG_HOME": folder, "XDG_CACHE_HOME": folder,
                   "XDG_DATA_HOME": folder, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            proc = subprocess.Popen([sys.executable, "-c", code], env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(marker.exists(), "worker did not start")
                proc.send_signal(signal.SIGINT)
                try:
                    _, stderr = proc.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    self.fail("runner did not stop the blocked worker promptly")
                self.assertEqual(proc.returncode, 130, stderr.decode())
            finally:
                if proc.poll() is None:
                    if marker.exists():
                        try:
                            os.kill(int(marker.read_text()), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.communicate()


if __name__ == "__main__":
    unittest.main()
