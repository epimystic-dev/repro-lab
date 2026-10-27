"""Scanner-layer tests: file reading, JSONL handling, dir walking."""

from __future__ import annotations

import json
import os
import unittest

from tests.support import rule_ids, run_cli, scan_string, write_temp

from evalrunlint.scanner import scan_file, scan_paths
from evalrunlint.types import Options


_HEALTHY = {
    "model": "org/m",
    "revision": "aa11bb22cc33",
    "num_fewshot": 5,
    "seed": 1,
    "limit": None,
    "bootstrap_iters": 1000,
    "enable_thinking": False,
    "git_hash": "deadbeef",
    "timestamp": "2026-10-01T00:00:00Z",
    "tasks": ["x"],
    "configs": {"x": {"num_fewshot": 5}},
    "results": {"x": {"acc": 0.5}},
}


class JsonAndJsonlInputs(unittest.TestCase):
    def test_single_json_object(self):
        d, p = write_temp(json.dumps(_HEALTHY), "r.json")
        try:
            res = scan_file(p, Options())
            self.assertEqual(res.records_scanned, 1)
            self.assertEqual([f.rule_id for f in res.findings], [])
        finally:
            _rm(d, p)

    def test_jsonl_two_records(self):
        body = json.dumps(_HEALTHY) + "\n" + json.dumps(_HEALTHY)
        d, p = write_temp(body, "r.jsonl")
        try:
            res = scan_file(p, Options())
            self.assertEqual(res.records_scanned, 2)
        finally:
            _rm(d, p)

    def test_json_array_of_records(self):
        body = json.dumps([_HEALTHY, _HEALTHY])
        d, p = write_temp(body, "r.json")
        try:
            res = scan_file(p, Options())
            self.assertEqual(res.records_scanned, 2)
        finally:
            _rm(d, p)

    def test_broken_json_reports_eval_000(self):
        d, p = write_temp("{not json", "broken.json")
        try:
            res = scan_file(p, Options())
            self.assertTrue(any(f.rule_id == "EVAL-000"
                                for f in res.findings))
        finally:
            _rm(d, p)

    def test_missing_file_reports_error(self):
        res = scan_file(
            os.path.join(os.getcwd(), "does_not_exist.json"), Options())
        self.assertEqual(res.files_scanned, 0)
        self.assertTrue(res.error)

    def test_scan_paths_walks_directory(self):
        d, p = write_temp(json.dumps(_HEALTHY), "r.json")
        try:
            res = scan_paths([d], Options())
            self.assertEqual(res.files_scanned, 1)
        finally:
            _rm(d, p)


class JsonOutputPipes(unittest.TestCase):
    def test_json_output_is_parsable(self):
        d, p = write_temp(json.dumps(_HEALTHY), "r.json")
        try:
            rc, out, _err = run_cli(["--json", p])
            self.assertEqual(rc, 0)
            obj = json.loads(out)
            self.assertEqual(obj["verdict"], "healthy")
            self.assertEqual(obj["files_scanned"], 1)
            self.assertEqual(obj["findings"], [])
        finally:
            _rm(d, p)


class DisableAndOnly(unittest.TestCase):
    def test_disable_suppresses_a_rule(self):
        bad = dict(_HEALTHY)
        bad.pop("revision")
        bad["model_args"] = "pretrained=org/m"
        bad.pop("model")
        bad["model"] = "org/m"  # no @ pin, no revision
        ids = rule_ids(scan_string(json.dumps(bad),
                                   Options(disabled=("EVAL-002",))))
        self.assertNotIn("EVAL-002", ids)

    def test_only_restricts_to_one_rule(self):
        bad = dict(_HEALTHY)
        bad.pop("seed")
        bad["model"] = "org/m"
        bad.pop("revision")
        bad["model_args"] = "pretrained=org/m"
        ids = rule_ids(scan_string(json.dumps(bad),
                                   Options(only=("EVAL-002",))))
        self.assertEqual(set(ids), {"EVAL-002"})


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
