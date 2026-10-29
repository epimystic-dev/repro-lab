"""Shared contract tests for nbexport."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from tests import support  # noqa: F401

import nbexport
from nbexport.cli import main
from nbexport.rules import REGISTRY


PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES_DIR = os.path.join(PKG_DIR, "examples")


def _run(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = PKG_DIR + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "nbexport", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class PackageSurfaceTests(unittest.TestCase):
    def test_version_str(self):
        self.assertIsInstance(nbexport.__version__, str)
        self.assertRegex(nbexport.__version__, r"^\d+\.\d+\.\d+$")

    def test_all_exports_present(self):
        for name in ("Severity", "Verdict", "Finding", "ScanResult",
                     "ALL_RULES", "Rule"):
            self.assertTrue(hasattr(nbexport, name), name)

    def test_shared_rule_table_alias_is_internal_registry(self):
        self.assertIs(nbexport.ALL_RULES, REGISTRY)

    def test_cli_main_callable(self):
        self.assertTrue(callable(main))

    def test_rule_ids_use_nbx_prefix(self):
        self.assertTrue(REGISTRY, "rule registry is empty")
        for r in REGISTRY:
            self.assertTrue(r.id.startswith("NBX-"), r.id)

    def test_every_rule_cites_a_public_source(self):
        for r in REGISTRY:
            self.assertTrue(r.citation.strip(), r.id)


class SharedContractInvariants(unittest.TestCase):
    def test_version_returns_zero(self):
        r = _run("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            r.stdout.strip(), "nbexport " + nbexport.__version__)

    def test_help_returns_zero(self):
        r = _run("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nbexport", r.stdout)

    def test_unknown_flag_returns_two(self):
        r = _run("--definitely-not-a-flag", "nonexistent.ipynb")
        self.assertEqual(r.returncode, 2)

    def test_known_clean_input_returns_zero(self):
        path = os.path.join(EXAMPLES_DIR, "healthy.ipynb")
        self.assertTrue(os.path.isfile(path))
        r = _run(path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_known_dirty_input_returns_nonzero(self):
        path = os.path.join(EXAMPLES_DIR, "dirty.ipynb")
        self.assertTrue(os.path.isfile(path))
        r = _run(path)
        self.assertNotEqual(r.returncode, 0)
        # Dirty fixture has non-monotonic execution_count.
        self.assertIn("NBX-002", r.stdout)


if __name__ == "__main__":
    unittest.main()
