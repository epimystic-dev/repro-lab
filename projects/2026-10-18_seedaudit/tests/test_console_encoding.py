"""Reporter must stay ASCII on cp1252 consoles."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from tests.support import write_temp


PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ReportStaysAsciiTests(unittest.TestCase):
    def test_cp1252_input_does_not_crash_reporter(self):
        # Fixture: a Python module whose docstring and a comment contain
        # a non-ASCII codepoint. The RNG call must still produce a
        # finding, and the reporter must emit <U+XXXX> rather than
        # raising UnicodeEncodeError.
        zwsp = chr(0x200B)
        cyr_a = chr(0x0430)
        content = (
            '"""Module docstring with ' + zwsp + 'invisible char."""\n'
            "# comment with Cyrillic " + cyr_a + "\n"
            "from sklearn.model_selection import train_test_split\n"
            "def f(X, y):\n"
            "    return train_test_split(X, y)\n"
        )
        _d, p = write_temp(content, "cp1252_in.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = PKG_DIR + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "cp1252"
        r = subprocess.run(
            [sys.executable, "-m", "seedaudit", p],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertNotIn(
            "UnicodeEncodeError", r.stderr, r.stderr)
        self.assertNotIn("Traceback", r.stderr, r.stderr)
        self.assertIn("SEED-005", r.stdout)
        # Non-ASCII characters should not leak into stdout verbatim;
        # but they may not even appear here (they live in the SOURCE,
        # not in finding messages). The assertion is that the reporter
        # itself did not crash.


if __name__ == "__main__":
    unittest.main()
