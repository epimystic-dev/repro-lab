"""Tests for every rule in seedaudit.rules.REGISTRY."""

from __future__ import annotations

import unittest

from seedaudit.rules import REGISTRY
from seedaudit.types import Options

from tests.support import rule_ids, scan_string


class RuleFiringTests(unittest.TestCase):
    def test_registry_has_seven_rules(self):
        self.assertEqual(len(REGISTRY), 7)

    def test_every_rule_has_prefix_and_citation(self):
        for r in REGISTRY:
            self.assertTrue(r.id.startswith("SEED-"), r.id)
            self.assertTrue(r.citation.strip(), r.id)

    def test_seed_001_stdlib_unseeded(self):
        ids = rule_ids(scan_string(
            "import random\n"
            "def f():\n"
            "    return random.random()\n"
        ))
        self.assertIn("SEED-001", ids)

    def test_seed_002_numpy_unseeded(self):
        ids = rule_ids(scan_string(
            "import numpy as np\n"
            "def f():\n"
            "    return np.random.rand(3)\n"
        ))
        self.assertIn("SEED-002", ids)

    def test_seed_003_torch_unseeded(self):
        ids = rule_ids(scan_string(
            "import torch\n"
            "def f():\n"
            "    return torch.randn(3)\n"
        ))
        self.assertIn("SEED-003", ids)

    def test_seed_004_tf_unseeded(self):
        ids = rule_ids(scan_string(
            "import tensorflow as tf\n"
            "def f():\n"
            "    return tf.random.uniform([3])\n"
        ))
        self.assertIn("SEED-004", ids)

    def test_seed_005_sklearn_split_without_random_state(self):
        ids = rule_ids(scan_string(
            "from sklearn.model_selection import train_test_split\n"
            "def f(X, y):\n"
            "    return train_test_split(X, y, test_size=0.2)\n"
        ))
        self.assertIn("SEED-005", ids)

    def test_seed_005_sklearn_split_with_random_state_is_clean(self):
        ids = rule_ids(scan_string(
            "from sklearn.model_selection import train_test_split\n"
            "def f(X, y):\n"
            "    return train_test_split(X, y, random_state=42)\n"
        ))
        self.assertNotIn("SEED-005", ids)

    def test_seed_005_stratified_shuffle_split_without_random_state(self):
        ids = rule_ids(scan_string(
            "from sklearn.model_selection import StratifiedShuffleSplit\n"
            "def f():\n"
            "    return StratifiedShuffleSplit(n_splits=5, test_size=0.2)\n"
        ))
        self.assertIn("SEED-005", ids)

    def test_seed_005_group_shuffle_split_without_random_state(self):
        ids = rule_ids(scan_string(
            "from sklearn.model_selection import GroupShuffleSplit\n"
            "def f():\n"
            "    return GroupShuffleSplit(n_splits=5)\n"
        ))
        self.assertIn("SEED-005", ids)

    def test_seed_005_stratified_group_kfold_without_random_state(self):
        ids = rule_ids(scan_string(
            "from sklearn.model_selection import StratifiedGroupKFold\n"
            "def f():\n"
            "    return StratifiedGroupKFold(n_splits=5)\n"
        ))
        self.assertIn("SEED-005", ids)

    def test_seed_005_repeated_kfold_without_random_state(self):
        ids = rule_ids(scan_string(
            "from sklearn.model_selection import RepeatedKFold\n"
            "def f():\n"
            "    return RepeatedKFold(n_splits=5, n_repeats=3)\n"
        ))
        self.assertIn("SEED-005", ids)

    def test_seed_005_repeated_stratified_kfold_without_random_state(self):
        ids = rule_ids(scan_string(
            "from sklearn.model_selection import RepeatedStratifiedKFold\n"
            "def f():\n"
            "    return RepeatedStratifiedKFold(n_splits=5, n_repeats=3)\n"
        ))
        self.assertIn("SEED-005", ids)

    def test_seed_005_repeated_kfold_with_random_state_is_clean(self):
        ids = rule_ids(scan_string(
            "from sklearn.model_selection import RepeatedKFold\n"
            "def f():\n"
            "    return RepeatedKFold(n_splits=5, n_repeats=3, random_state=0)\n"
        ))
        self.assertNotIn("SEED-005", ids)

    def test_seed_006_reseed_in_function(self):
        # SEED-006 is INFO - need include_info=True (or strict).
        ids = rule_ids(scan_string(
            "import numpy as np\n"
            "def f():\n"
            "    np.random.seed(1)\n"
            "    np.random.rand()\n"
            "    np.random.seed(2)\n"
            "    np.random.rand()\n",
            options=Options(include_info=True),
        ))
        self.assertIn("SEED-006", ids)

    def test_seed_007_seed_declared_but_unused(self):
        ids = rule_ids(scan_string(
            "import numpy as np\n"
            "np.random.seed(42)\n"
            "def f(x):\n"
            "    return x + 1\n",
            options=Options(include_info=True),
        ))
        self.assertIn("SEED-007", ids)

    def test_module_level_seed_silences_findings(self):
        ids = rule_ids(scan_string(
            "import random\n"
            "import numpy as np\n"
            "import torch\n"
            "random.seed(1)\n"
            "np.random.seed(2)\n"
            "torch.manual_seed(3)\n"
            "def f():\n"
            "    return (random.random(), np.random.rand(), torch.randn(2))\n"
        ))
        self.assertNotIn("SEED-001", ids)
        self.assertNotIn("SEED-002", ids)
        self.assertNotIn("SEED-003", ids)

    def test_seed_kwarg_silences_findings(self):
        ids = rule_ids(scan_string(
            "import numpy as np\n"
            "def f():\n"
            "    return np.random.rand(3)\n",
        ))
        # Baseline: without seed kwarg, SEED-002 fires.
        self.assertIn("SEED-002", ids)
        # Does an explicit seed= kwarg silence it? NumPy's legacy
        # top-level API does not accept seed=, but Generator methods do.
        # The analyzer treats seed=/random_state=/generator= as "locally
        # seeded" uniformly; so adding seed= to np.random.rand will
        # silence the finding even though NumPy itself would ignore it.
        # That is a documented false-negative; test for the silence here.
        ids2 = rule_ids(scan_string(
            "import numpy as np\n"
            "def f():\n"
            "    return np.random.rand(seed=1)\n",
        ))
        self.assertNotIn("SEED-002", ids2)


if __name__ == "__main__":
    unittest.main()
