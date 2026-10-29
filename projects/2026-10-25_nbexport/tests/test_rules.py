"""Behavioural tests for each NBX-* rule."""

from __future__ import annotations

import unittest

from tests.support import (
    code_cell, make_notebook, rule_ids, scan_string,
)

from nbexport.types import Options, Severity
from nbexport.rules import REGISTRY


class HealthyBaseline(unittest.TestCase):
    def test_healthy_notebook_fires_no_rules(self):
        nb = make_notebook(cells=[
            code_cell("import math\n", execution_count=1),
            code_cell("x = math.pi\n", execution_count=2),
            code_cell("print(x)\n", execution_count=3),
        ])
        ids = rule_ids(scan_string(nb, Options(include_info=True)))
        self.assertEqual(list(ids), [])


class Nbx001NullBetweenExecuted(unittest.TestCase):
    def test_null_cell_between_executed(self):
        nb = make_notebook(cells=[
            code_cell("import math\n", execution_count=1),
            code_cell("y = 1\n", execution_count=None),
            code_cell("print(math.pi)\n", execution_count=2),
        ])
        self.assertIn("NBX-001", rule_ids(scan_string(nb)))

    def test_trailing_null_is_fine(self):
        nb = make_notebook(cells=[
            code_cell("import math\n", execution_count=1),
            code_cell("print(math.pi)\n", execution_count=2),
            code_cell("# work in progress\n", execution_count=None),
        ])
        self.assertNotIn("NBX-001", rule_ids(scan_string(nb)))


class Nbx002NonMonotonicExecution(unittest.TestCase):
    def test_out_of_order_executions(self):
        nb = make_notebook(cells=[
            code_cell("a = 1\n", execution_count=3),
            code_cell("b = 2\n", execution_count=1),
            code_cell("c = 3\n", execution_count=2),
        ])
        self.assertIn("NBX-002", rule_ids(scan_string(nb)))

    def test_monotonic_passes(self):
        nb = make_notebook(cells=[
            code_cell("a = 1\n", execution_count=1),
            code_cell("b = 2\n", execution_count=2),
            code_cell("c = 3\n", execution_count=3),
        ])
        self.assertNotIn("NBX-002", rule_ids(scan_string(nb)))


class Nbx003DuplicateExecutionCount(unittest.TestCase):
    def test_duplicate_ec_fires(self):
        nb = make_notebook(cells=[
            code_cell("a = 1\n", execution_count=1),
            code_cell("b = 2\n", execution_count=2),
            code_cell("c = 3\n", execution_count=2),
        ])
        self.assertIn("NBX-003", rule_ids(scan_string(nb)))


class Nbx004ExecutionCountGaps(unittest.TestCase):
    def test_gap_fires_info(self):
        nb = make_notebook(cells=[
            code_cell("a = 1\n", execution_count=1),
            code_cell("c = 3\n", execution_count=3),
        ])
        ids = rule_ids(scan_string(nb, Options(include_info=True)))
        self.assertIn("NBX-004", ids)

    def test_no_gap_passes(self):
        nb = make_notebook(cells=[
            code_cell("a = 1\n", execution_count=1),
            code_cell("b = 2\n", execution_count=2),
            code_cell("c = 3\n", execution_count=3),
        ])
        self.assertNotIn("NBX-004",
                         rule_ids(scan_string(nb, Options(include_info=True))))


class Nbx005MagicOrShell(unittest.TestCase):
    def test_line_magic_fires(self):
        nb = make_notebook(cells=[
            code_cell("%matplotlib inline\nimport math\n",
                      execution_count=1),
        ])
        self.assertIn("NBX-005", rule_ids(scan_string(nb)))

    def test_shell_command_fires(self):
        nb = make_notebook(cells=[
            code_cell("!pip install numpy\n", execution_count=1),
        ])
        self.assertIn("NBX-005", rule_ids(scan_string(nb)))


class Nbx006ImportAfterUse(unittest.TestCase):
    def test_use_before_import_fires(self):
        nb = make_notebook(cells=[
            # ec=2: uses math
            code_cell("print(math.pi)\n", execution_count=2),
            # ec=3: imports math (so EC 2 ran without this import)
            code_cell("import math\n", execution_count=3),
        ])
        self.assertIn("NBX-006", rule_ids(scan_string(nb)))

    def test_import_then_use_passes(self):
        nb = make_notebook(cells=[
            code_cell("import math\n", execution_count=1),
            code_cell("print(math.pi)\n", execution_count=2),
        ])
        self.assertNotIn("NBX-006", rule_ids(scan_string(nb)))


class Nbx007MissingKernelspec(unittest.TestCase):
    def test_no_kernelspec_fires(self):
        nb = make_notebook(cells=[
            code_cell("x = 1\n", execution_count=1),
        ], kernel_name="")
        self.assertIn("NBX-007", rule_ids(scan_string(nb)))


class Nbx008NonPythonLanguage(unittest.TestCase):
    def test_r_language_fires_info(self):
        nb = make_notebook(cells=[
            code_cell("x <- 1\n", execution_count=1),
        ], language_name="r")
        self.assertIn("NBX-008",
                      rule_ids(scan_string(nb, Options(include_info=True))))


class Nbx009ExecutedButEmpty(unittest.TestCase):
    def test_executed_empty_source_fires(self):
        nb = make_notebook(cells=[
            code_cell("", execution_count=1),
            code_cell("x = 1\n", execution_count=2),
        ])
        self.assertIn("NBX-009", rule_ids(scan_string(nb)))


class RuleRegistryShape(unittest.TestCase):
    def test_rule_ids_unique(self):
        ids = [r.id for r in REGISTRY]
        self.assertEqual(len(ids), len(set(ids)))

    def test_severity_values_valid(self):
        for r in REGISTRY:
            self.assertIn(r.severity, (Severity.HIGH, Severity.MEDIUM,
                                       Severity.INFO))


if __name__ == "__main__":
    unittest.main()
