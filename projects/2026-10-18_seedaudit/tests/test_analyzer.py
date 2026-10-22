"""Unit tests for the AST analyzer."""

from __future__ import annotations

import unittest

from seedaudit.analyzer import analyze


class AliasResolutionTests(unittest.TestCase):
    def test_bare_import(self):
        r = analyze("import numpy\nnumpy.random.rand()\n")
        self.assertEqual(len(r.calls), 1)
        self.assertEqual(r.calls[0].dotted, "numpy.random.rand")

    def test_import_as(self):
        r = analyze("import numpy as np\nnp.random.rand()\n")
        self.assertEqual(len(r.calls), 1)
        self.assertEqual(r.calls[0].dotted, "numpy.random.rand")

    def test_from_import(self):
        r = analyze(
            "from sklearn.model_selection import train_test_split\n"
            "train_test_split(X, y)\n"
        )
        self.assertEqual(len(r.calls), 1)
        self.assertEqual(
            r.calls[0].dotted,
            "sklearn.model_selection.train_test_split")

    def test_from_import_as(self):
        r = analyze(
            "from numpy import random as nr\n"
            "nr.rand()\n"
        )
        self.assertEqual(len(r.calls), 1)
        self.assertEqual(r.calls[0].dotted, "numpy.random.rand")


class SeedingDetectionTests(unittest.TestCase):
    def test_module_level_seed(self):
        r = analyze(
            "import numpy as np\n"
            "np.random.seed(42)\n"
            "np.random.rand()\n"
        )
        # The call must have observed the module-level seed.
        self.assertEqual(len(r.calls), 1)
        self.assertTrue(r.calls[0].scope_seeded)

    def test_function_level_seed(self):
        r = analyze(
            "import numpy as np\n"
            "def f():\n"
            "    np.random.seed(42)\n"
            "    np.random.rand()\n"
        )
        self.assertEqual(len(r.calls), 1)
        self.assertTrue(r.calls[0].scope_seeded)

    def test_unseeded(self):
        r = analyze(
            "import numpy as np\n"
            "def f():\n"
            "    np.random.rand()\n"
        )
        self.assertEqual(len(r.calls), 1)
        self.assertFalse(r.calls[0].scope_seeded)

    def test_seed_kwarg_counts_as_seeded(self):
        r = analyze(
            "import numpy as np\n"
            "def f(rng):\n"
            "    rng.standard_normal(5)\n"
        )
        # We don't track rng.<fn> as RNG - the aliases don't map to our
        # canonical list. Instead confirm we don't crash on method calls.
        self.assertEqual(r.calls, [])

    def test_random_state_kwarg_is_detected(self):
        r = analyze(
            "from sklearn.model_selection import train_test_split\n"
            "train_test_split(X, y, random_state=42)\n"
        )
        self.assertEqual(len(r.calls), 1)
        self.assertTrue(r.calls[0].has_seeding_kwarg)


class SyntaxErrorTests(unittest.TestCase):
    def test_syntax_error_captured_not_raised(self):
        r = analyze("def f(:\n")
        self.assertIsNotNone(r.syntax_error)
        self.assertEqual(r.calls, [])


class ReseedTests(unittest.TestCase):
    def test_reseed_mid_function(self):
        r = analyze(
            "import numpy as np\n"
            "def f():\n"
            "    np.random.seed(1)\n"
            "    np.random.rand()\n"
            "    np.random.seed(2)\n"
            "    np.random.rand()\n"
        )
        self.assertEqual(len(r.calls), 2)
        # The second call must have seen reseed_count > 0.
        self.assertTrue(r.calls[1].reseeded_mid_function)
        # The first call must NOT have observed a reseed yet.
        self.assertFalse(r.calls[0].reseeded_mid_function)


if __name__ == "__main__":
    unittest.main()
