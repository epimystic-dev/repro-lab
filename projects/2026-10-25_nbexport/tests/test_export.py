"""Tests for the script-export subcommand."""

from __future__ import annotations

import os
import unittest

from tests.support import (
    code_cell, make_notebook, run_cli, write_temp,
)

from nbexport.export import emit_script
from nbexport.notebook import parse_notebook


class ScriptEmission(unittest.TestCase):
    def test_linear_mode_preserves_file_order(self):
        nb = parse_notebook(make_notebook(cells=[
            code_cell("a = 1\n", execution_count=3),
            code_cell("b = 2\n", execution_count=1),
            code_cell("c = 3\n", execution_count=2),
        ]))
        script = emit_script(nb, "linear")
        self.assertLess(script.index("a = 1"), script.index("b = 2"))
        self.assertLess(script.index("b = 2"), script.index("c = 3"))

    def test_executed_mode_sorts_by_execution_count(self):
        nb = parse_notebook(make_notebook(cells=[
            code_cell("a = 1\n", execution_count=3),
            code_cell("b = 2\n", execution_count=1),
            code_cell("c = 3\n", execution_count=2),
        ]))
        script = emit_script(nb, "executed")
        # Order should be b, c, a (ec 1, 2, 3).
        self.assertLess(script.index("b = 2"), script.index("c = 3"))
        self.assertLess(script.index("c = 3"), script.index("a = 1"))

    def test_executed_mode_appends_never_run_cells_last(self):
        nb = parse_notebook(make_notebook(cells=[
            code_cell("a = 1\n", execution_count=1),
            code_cell("b = 2\n", execution_count=None),
            code_cell("c = 3\n", execution_count=2),
        ]))
        script = emit_script(nb, "executed")
        self.assertLess(script.index("a = 1"), script.index("b = 2"))
        self.assertLess(script.index("c = 3"), script.index("b = 2"))

    def test_magic_lines_are_commented_out(self):
        nb = parse_notebook(make_notebook(cells=[
            code_cell("%matplotlib inline\nx = 1\n", execution_count=1),
            code_cell("!pip install numpy\n", execution_count=2),
        ]))
        script = emit_script(nb, "linear")
        self.assertIn("# nbexport: %matplotlib inline", script)
        self.assertIn("# nbexport: !pip install numpy", script)
        # Non-magic code stays uncommented.
        self.assertIn("\nx = 1\n", script)

    def test_ipython_help_lines_are_commented_out(self):
        # `?open` and `??print` are SyntaxErrors under plain Python;
        # the emitted script must not carry them through verbatim.
        nb = parse_notebook(make_notebook(cells=[
            code_cell("?open\nx = 1\n", execution_count=1),
            code_cell("??print\n", execution_count=2),
        ]))
        script = emit_script(nb, "linear")
        self.assertIn("# nbexport: ?open", script)
        self.assertIn("# nbexport: ??print", script)
        self.assertIn("\nx = 1\n", script)
        # Guard: the emitted script compiles under plain Python.
        compile(script, "<emitted>", "exec")


class EmitScriptCliFlag(unittest.TestCase):
    def test_emit_script_writes_file(self):
        content = make_notebook(cells=[
            code_cell("x = 1\n", execution_count=1),
            code_cell("y = 2\n", execution_count=2),
        ])
        d, p = write_temp(content, "nb.ipynb")
        out_path = os.path.join(d, "nb.py")
        try:
            rc, _out, _err = run_cli([
                "--emit-script", "linear", "-o", out_path, p,
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path, "r", encoding="utf-8") as f:
                body = f.read()
            self.assertIn("x = 1", body)
            self.assertIn("y = 2", body)
            self.assertIn("LINEAR", body)
        finally:
            for name in ("nb.ipynb", "nb.py"):
                fp = os.path.join(d, name)
                if os.path.isfile(fp):
                    os.remove(fp)
            try:
                os.rmdir(d)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
