"""The reporter must never crash on a cp1252 console.

A Windows console on code page 1252 cannot encode a zero-width space or
a Cyrillic letter; echoing one raw crashes the reporter mid-write with
a traceback and no finding. The reporter MUST render any non-ASCII as
``<U+XXXX>`` instead of passing it through. This is tested against the
real CLI via subprocess with PYTHONIOENCODING=cp1252.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from tests.support import write_temp


PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(path: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = PKG_DIR + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run(
        [sys.executable, "-m", "evalrunlint", path],
        capture_output=True,
        text=False,  # bytes so we can see what the stream actually got
        env=env,
        timeout=30,
    )


class ConsoleEncodingSafety(unittest.TestCase):
    def test_zero_width_space_in_model_name_is_safe(self):
        # Assemble the zero-width space without an inline non-ASCII literal.
        zwsp = chr(0x200B)  # ZERO WIDTH SPACE
        rec = {
            "model": "org/model" + zwsp,
            "model_args": "pretrained=org/model" + zwsp,
            # No revision -> EVAL-002 fires on this model name.
            "num_fewshot": 5,
            "seed": 1,
            "limit": None,
            "bootstrap_iters": 1000,
            "git_hash": "deadbeef",
            "timestamp": "2026-10-01T00:00:00Z",
            "tasks": ["x"],
            "configs": {"x": {"num_fewshot": 5}},
            "results": {"x": {"acc": 0.5}},
        }
        d, p = write_temp(json.dumps(rec), "zwsp.json")
        try:
            r = _run(p)
            # No traceback on the console.
            self.assertNotIn(b"Traceback", r.stderr,
                             "reporter crashed on a cp1252 console")
            # The rule still fires on stdout.
            self.assertIn(b"EVAL-002", r.stdout)
            # The hidden char is surfaced visibly in the report.
            self.assertIn(b"<U+200B>", r.stdout)
        finally:
            try:
                os.remove(p)
                os.rmdir(d)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
