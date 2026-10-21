"""Shared contract tests for doicheck.

Two contracts are locked here:

1. Package-surface invariants - the public API this module exports:
   ``__version__``, ``Severity``, ``Verdict``, ``Finding``, ``ScanResult``,
   ``ALL_RULES``, ``Rule``, plus the DOI-* rule-ID convention.

2. CI-consumer invariants from repro-lab/docs/CONVENTIONS.md, locked
   against the ``python -m <tool>`` subprocess entry:

     a. ``python -m doicheck --help`` returns rc 0.
     b. ``python -m doicheck`` on a known-clean input returns rc 0.
     c. ``python -m doicheck`` on a known-dirty input returns non-zero
        with the DOI-013 anchor on stdout (the dirty fixture has a
        duplicate cite key).
     d. An unknown flag returns rc 2.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from tests import support  # noqa: F401

import doicheck
from doicheck.cli import main
from doicheck.rules import REGISTRY


PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES_DIR = os.path.join(PKG_DIR, "examples")


def _run(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = PKG_DIR + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "doicheck", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class PackageSurfaceTests(unittest.TestCase):
    def test_version_str(self):
        self.assertIsInstance(doicheck.__version__, str)
        self.assertRegex(doicheck.__version__, r"^\d+\.\d+\.\d+$")

    def test_all_exports_present(self):
        for name in ("Severity", "Verdict", "Finding", "ScanResult",
                     "ALL_RULES", "Rule"):
            self.assertTrue(hasattr(doicheck, name), name)

    def test_shared_rule_table_alias_is_internal_registry(self):
        self.assertIs(doicheck.ALL_RULES, REGISTRY)

    def test_cli_main_callable(self):
        self.assertTrue(callable(main))

    def test_rule_ids_use_doi_prefix(self):
        self.assertTrue(REGISTRY, "rule registry is empty")
        for r in REGISTRY:
            self.assertTrue(r.id.startswith("DOI-"), r.id)

    def test_every_rule_cites_a_public_source(self):
        for r in REGISTRY:
            self.assertTrue(r.citation.strip(), r.id)


class SharedContractInvariants(unittest.TestCase):
    def test_version_returns_zero_without_a_path(self):
        r = _run("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            r.stdout.strip(), "doicheck " + doicheck.__version__)

    def test_help_returns_zero(self):
        r = _run("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("doicheck", r.stdout)

    def test_unknown_flag_returns_two(self):
        r = _run("--definitely-not-a-flag", "nonexistent.bib")
        self.assertEqual(r.returncode, 2)

    def test_known_clean_input_returns_zero(self):
        path = os.path.join(EXAMPLES_DIR, "healthy.bib")
        self.assertTrue(os.path.isfile(path))
        r = _run(path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_known_dirty_input_returns_nonzero(self):
        path = os.path.join(EXAMPLES_DIR, "dirty.bib")
        self.assertTrue(os.path.isfile(path))
        r = _run(path)
        self.assertNotEqual(
            r.returncode, 0,
            "doicheck exited 0 on a known-dirty input",
        )
        # The dirty fixture has a duplicate cite key.
        self.assertIn(
            "DOI-013", r.stdout,
            "expected DOI-013 anchor on dirty fixture; stdout: "
            + repr(r.stdout),
        )


if __name__ == "__main__":
    unittest.main()
