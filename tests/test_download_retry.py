"""A mirrors.ctan.org download is asked again when the mirror that answered was bad (no network: every opener is a stand-in)."""

import hashlib
import io
import ssl
import socket
import sys
import unittest
import urllib.error
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from pdfmd_unicode import install  # noqa: E402
from pdfmd_unicode.download import fetch, retries_setting  # noqa: E402

CTAN = "https://mirrors.ctan.org/fonts/x.zip"
OTHER = "https://example.invalid/x.zip"
CERT = urllib.error.URLError(ssl.SSLCertVerificationError(
    "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate"))


class Reply:
    def __init__(self, data, final="https://good.mirror.example/x.zip"):
        self.data, self.final = data, final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.data

    def geturl(self):
        return self.final


def opener_of(*steps):
    """Each call takes the next step: an exception is raised, bytes are answered."""
    calls = []

    def opener(request, timeout=None):
        calls.append(request.full_url)
        step = steps[min(len(calls), len(steps)) - 1]
        if isinstance(step, BaseException):
            raise step
        return Reply(step)
    opener.calls = calls
    return opener


class Fetch(unittest.TestCase):
    def test_a_certificate_error_is_retried_and_the_next_mirror_serves(self):
        opener, log = opener_of(CERT, b"data"), []
        self.assertEqual(fetch(CTAN, opener, log.append, retries=2), b"data")
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual(len(log), 1)
        self.assertTrue(log[0].startswith("WARN"))
        self.assertIn("CERTIFICATE_VERIFY_FAILED", log[0])

    def test_every_try_failing_raises_the_last_error_after_the_extra_tries(self):
        opener, log = opener_of(CERT), []
        with self.assertRaises(urllib.error.URLError) as caught:
            fetch(CTAN, opener, log.append, retries=2)
        self.assertIs(caught.exception, CERT)
        self.assertEqual(len(opener.calls), 3, "one try and two extra")
        self.assertEqual(len(log), 2, "the final failure is the raised error, not a warning")

    def test_zero_is_one_try(self):
        opener, log = opener_of(CERT), []
        with self.assertRaises(urllib.error.URLError):
            fetch(CTAN, opener, log.append, retries=0)
        self.assertEqual((len(opener.calls), log), (1, []))

    def test_a_negative_number_keeps_asking_until_a_mirror_answers(self):
        opener, log = opener_of(*([CERT] * 7 + [ConnectionResetError("reset"), TimeoutError("slow"), b"ok"])), []
        self.assertEqual(fetch(CTAN, opener, log.append, retries=-1), b"ok")
        self.assertEqual((len(opener.calls), len(log)), (10, 9))

    def test_a_checksum_mismatch_is_retried_and_the_warning_names_the_mirror(self):
        good = b"the right bytes"

        def check(data):
            if data != good:
                raise install.ChecksumMismatch("SHA-256 mismatch")
        opener, log = opener_of(b"corrupt", good), []
        self.assertEqual(fetch(CTAN, opener, log.append, retries=1, check=check), good)
        self.assertEqual(len(log), 1)
        self.assertIn("good.mirror.example", log[0])
        self.assertIn("SHA-256 mismatch", log[0])

    def test_dns_retry_only_for_temporary_resolution_on_redirector(self):
        temporary = urllib.error.URLError(socket.gaierror(socket.EAI_AGAIN, "temporary"))
        permanent = urllib.error.URLError(socket.gaierror(socket.EAI_NONAME, "unknown"))
        opener = opener_of(temporary, b"ok")
        self.assertEqual(fetch(CTAN, opener, lambda line: None, retries=1), b"ok")
        self.assertEqual(len(opener.calls), 2)
        for url, error in ((CTAN, permanent), (OTHER, temporary)):
            with self.subTest(url=url):
                opener = opener_of(error, b"ok")
                with self.assertRaises(urllib.error.URLError):
                    fetch(url, opener, lambda line: None, retries=1)
                self.assertEqual(len(opener.calls), 1)

    def test_another_host_is_never_retried(self):
        opener = opener_of(CERT)
        with self.assertRaises(urllib.error.URLError):
            fetch(OTHER, opener, lambda line: None, retries=5)
        self.assertEqual(len(opener.calls), 1)

    def test_an_http_status_is_not_retried(self):
        error = urllib.error.HTTPError(CTAN, 404, "Not Found", {}, io.BytesIO())
        opener = opener_of(error)
        with self.assertRaises(urllib.error.HTTPError):
            fetch(CTAN, opener, lambda line: None, retries=5)
        self.assertEqual(len(opener.calls), 1)

    def test_the_setting_zero_negative_positive_and_unset(self):
        class Core:
            def __init__(self, value):
                self.value = value

            def option_flag_number(self, value):
                return None if value is None else float(value)

            def config_options(self):
                return {} if self.value is None else {"download-retries": self.value}
        self.assertEqual([retries_setting(Core(v)) for v in (None, 0, 5, -1)], [2, 0, 5, -1])


class Installing(unittest.TestCase):
    def test_a_zip_with_a_bad_checksum_is_retried_through_install(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("pkg/a.otf", b"font")
        archive = buffer.getvalue()
        package = {"title": "T", "license": "OFL", "homepage": "h", "size": 1, "scripts": [],
                   "files": [{"zip": CTAN, "zip_sha256": hashlib.sha256(archive).hexdigest(), "member": "pkg/a.otf", "name": "a.otf", "size": 4}]}
        real = install.PACKAGES
        install.PACKAGES = {"t": package}
        self.addCleanup(lambda: setattr(install, "PACKAGES", real))
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            log = []
            failed = install.install(["t"], Path(folder), log=log.append, opener=opener_of(b"corrupt", archive), retries=2)
            self.assertEqual(failed, [])
            self.assertEqual((Path(folder) / "t" / "a.otf").read_bytes(), b"font")
            self.assertEqual(sum(line.startswith("WARN") for line in log), 1)
            log.clear()
            failed = install.install(["t"], Path(folder), log=log.append, opener=opener_of(b"corrupt"), retries=0)
            self.assertEqual(failed, ["t"])
            self.assertTrue(any("SHA-256 mismatch" in line for line in log))


if __name__ == "__main__":
    unittest.main()
