"""The report must never crash on a console that cannot encode what
it is reporting. A Windows console on code page 1252 cannot encode a
Cyrillic letter or a zero-width space; echoing one raw crashes the
reporter mid-write (traceback, no finding). The reporter renders every
character outside printable ASCII as ``<U+XXXX>``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from tests import support
from tests.support import write_temp


PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ReportStaysAsciiTests(unittest.TestCase):
    def test_cp1252_input_does_not_crash_reporter(self):
        # Fixture: a BibTeX entry with a non-ASCII title containing a
        # zero-width space (U+200B) and a Cyrillic letter (U+0430). Both
        # are codepoints a Windows cp1252 console cannot encode raw.
        zwsp = chr(0x200B)
        cyr_a = chr(0x0430)
        content = (
            "@article{bad,\n"
            "  author = {A},\n"
            "  title = {A paper with " + zwsp + cyr_a + " and dup},\n"
            "  journal = {J},\n"
            "  year = {2020}\n"
            "}\n"
            "@article{bad,\n"
            "  author = {B},\n"
            "  title = {dup key},\n"
            "  journal = {J},\n"
            "  year = {2020}\n"
            "}\n"
        )
        _d, p = write_temp(content, "cp1252.bib")
        env = os.environ.copy()
        env["PYTHONPATH"] = PKG_DIR + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "cp1252"
        r = subprocess.run(
            [sys.executable, "-m", "doicheck", p],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertNotIn(
            "UnicodeEncodeError", r.stderr,
            "reporter crashed on cp1252 console",
        )
        self.assertNotIn("Traceback", r.stderr, r.stderr)
        self.assertIn("DOI-013", r.stdout)
        # Non-ASCII must be rendered as <U+XXXX>, never echoed raw.
        self.assertNotIn(zwsp, r.stdout)
        self.assertNotIn(cyr_a, r.stdout)


if __name__ == "__main__":
    unittest.main()
