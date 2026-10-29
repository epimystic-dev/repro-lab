"""The reporter must not crash on a cp1252 console.

A notebook with a non-ASCII cell path or source produces findings that
mention the path and may mention the subject. The reporter must render
anything outside printable ASCII as ``<U+XXXX>`` so the stream never
hits an encode error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from tests.support import code_cell, make_notebook, write_temp


PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(path: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = PKG_DIR + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run(
        [sys.executable, "-m", "nbexport", path],
        capture_output=True,
        text=False,
        env=env,
        timeout=30,
    )


class ConsoleEncodingSafety(unittest.TestCase):
    def test_zero_width_space_in_cell_source_is_safe(self):
        # The ZERO WIDTH SPACE is a classic smuggled char. Build the
        # fixture via chr() so no non-ASCII literal appears in source.
        zwsp = chr(0x200B)
        content = make_notebook(cells=[
            code_cell("a = 1\n" + zwsp + "\n", execution_count=1),
        ])
        d, p = write_temp(content, "zwsp.ipynb")
        try:
            r = _run(p)
            # Reporter did not crash.
            self.assertNotIn(b"Traceback", r.stderr)
            # The CLI did not fail with an encoding error either.
            self.assertNotIn(b"UnicodeEncodeError", r.stderr)
        finally:
            try:
                os.remove(p)
                os.rmdir(d)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
