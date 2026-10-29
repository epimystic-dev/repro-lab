"""Scanner-layer tests: file reading, directory walking, broken input."""

from __future__ import annotations

import json
import os
import unittest

from tests.support import (
    code_cell, make_notebook, rule_ids, run_cli, write_temp,
)

from nbexport.scanner import scan_file, scan_paths
from nbexport.types import Options


class FileAndDirectoryInputs(unittest.TestCase):
    def test_single_notebook(self):
        d, p = write_temp(make_notebook(cells=[
            code_cell("x = 1\n", execution_count=1),
        ]))
        try:
            res = scan_file(p, Options())
            self.assertEqual(res.code_cells_scanned, 1)
            self.assertEqual([f.rule_id for f in res.findings], [])
        finally:
            _rm(d, p)

    def test_broken_json_reports_nbx_000(self):
        d, p = write_temp("{not json", "broken.ipynb")
        try:
            res = scan_file(p, Options())
            self.assertTrue(any(f.rule_id == "NBX-000"
                                for f in res.findings))
        finally:
            _rm(d, p)

    def test_missing_file_reports_error(self):
        res = scan_file(os.path.join(os.getcwd(),
                                      "does_not_exist.ipynb"), Options())
        self.assertEqual(res.files_scanned, 0)
        self.assertTrue(res.error)

    def test_scan_paths_walks_directory(self):
        d, p = write_temp(make_notebook(cells=[
            code_cell("x = 1\n", execution_count=1),
        ]), "a.ipynb")
        try:
            res = scan_paths([d], Options())
            self.assertEqual(res.files_scanned, 1)
        finally:
            _rm(d, p)


class JsonOutputPipes(unittest.TestCase):
    def test_json_output_is_parsable(self):
        content = make_notebook(cells=[
            code_cell("x = 1\n", execution_count=1),
        ])
        d, p = write_temp(content)
        try:
            rc, out, _err = run_cli(["--json", p])
            self.assertEqual(rc, 0)
            obj = json.loads(out)
            self.assertEqual(obj["verdict"], "healthy")
            self.assertEqual(obj["code_cells_scanned"], 1)
        finally:
            _rm(d, p)


class DisableAndOnly(unittest.TestCase):
    def test_disable_suppresses_rule(self):
        nb = make_notebook(cells=[
            code_cell("a = 1\n", execution_count=2),
            code_cell("b = 2\n", execution_count=1),
        ])
        from nbexport.rules import run_all
        ids = tuple(f.rule_id for f in run_all(
            nb, "x.ipynb", Options(disabled=("NBX-002",))))
        self.assertNotIn("NBX-002", ids)


def _rm(d, p):
    try:
        os.remove(p)
    finally:
        try:
            os.rmdir(d)
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()
