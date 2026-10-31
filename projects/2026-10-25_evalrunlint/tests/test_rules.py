"""Behavioural tests for each EVAL-* rule.

Fixtures are JSON strings assembled inline so a reader can see exactly
what each rule reacts to. Each test asserts a specific rule fires (or
does not), rather than aggregate counts, so a future refactor can only
regress one check at a time.
"""

from __future__ import annotations

import json
import unittest

from tests.support import rule_ids, scan_string

from evalrunlint.types import Options, Severity
from evalrunlint.rules import REGISTRY


# A base record that is maximally healthy. Individual tests mutate.
_BASE = {
    "model": "org/model",
    "model_args": "pretrained=org/model,revision=abc123def456",
    "revision": "abc123def456",
    "num_fewshot": 5,
    "seed": 1234,
    "limit": None,
    "bootstrap_iters": 1000,
    "enable_thinking": False,
    "git_hash": "harness-v0.4.13-deadbeef",
    "timestamp": "2026-10-20T12:00:00Z",
    "tasks": ["mmlu_college_physics"],
    "configs": {"mmlu_college_physics": {"num_fewshot": 5}},
    "results": {
        "mmlu_college_physics": {"acc": 0.65, "acc_stderr": 0.01,
                                  "n_samples": 102}
    },
}


def _record(**overrides):
    import copy
    r = copy.deepcopy(_BASE)
    for k, v in overrides.items():
        if v is _DELETE:
            r.pop(k, None)
        else:
            r[k] = v
    return json.dumps(r)


class _Sentinel:
    pass


_DELETE = _Sentinel()


class HealthyBaseline(unittest.TestCase):
    def test_healthy_fires_no_rules(self):
        ids = rule_ids(scan_string(_record(), Options(include_info=True)))
        self.assertEqual(
            [i for i in ids if i != "EVAL-015"], [],
            "unexpected findings: " + ",".join(ids),
        )
        # Harness git is present in the base, so EVAL-015 should not fire.
        self.assertNotIn("EVAL-015", ids)


class Eval001NoModel(unittest.TestCase):
    def test_record_without_model(self):
        ids = rule_ids(scan_string(_record(
            model=_DELETE, model_args=_DELETE,
            revision=_DELETE,
        )))
        self.assertIn("EVAL-001", ids)

    def test_record_with_model_does_not_fire(self):
        self.assertNotIn("EVAL-001", rule_ids(scan_string(_record())))


class Eval002UnpinnedModel(unittest.TestCase):
    def test_no_revision_is_unpinned(self):
        ids = rule_ids(scan_string(_record(
            revision=_DELETE,
            model_args="pretrained=org/model",
        )))
        self.assertIn("EVAL-002", ids)

    def test_at_suffix_treated_as_pin(self):
        ids = rule_ids(scan_string(_record(
            model="org/model@abc123def456",
            revision=_DELETE,
            model_args=_DELETE,
        )))
        self.assertNotIn("EVAL-002", ids)

    def test_main_branch_suffix_is_not_a_pin(self):
        ids = rule_ids(scan_string(_record(
            model="org/model@main",
            revision=_DELETE,
            model_args=_DELETE,
        )))
        self.assertIn("EVAL-002", ids)

    def test_revision_field_set_to_main_is_not_a_pin(self):
        # Symmetric case to test_main_branch_suffix_is_not_a_pin: the
        # explicit revision field carries the same branch-name
        # false-positive risk as the @suffix form.
        ids = rule_ids(scan_string(_record(
            model="org/model",
            revision="main",
            model_args="pretrained=org/model",
        )))
        self.assertIn("EVAL-002", ids)

    def test_revision_field_set_to_master_is_not_a_pin(self):
        ids = rule_ids(scan_string(_record(
            model="org/model",
            revision="master",
            model_args="pretrained=org/model",
        )))
        self.assertIn("EVAL-002", ids)

    def test_revision_field_set_to_head_is_case_insensitive(self):
        ids = rule_ids(scan_string(_record(
            model="org/model",
            revision="HEAD",
            model_args="pretrained=org/model",
        )))
        self.assertIn("EVAL-002", ids)

    def test_revision_field_set_to_sha_is_a_pin(self):
        # Guard against over-reach: a real sha must still be accepted.
        ids = rule_ids(scan_string(_record(
            model="org/model",
            revision="abc123def456",
            model_args="pretrained=org/model",
        )))
        self.assertNotIn("EVAL-002", ids)

    def test_model_args_revision_main_is_not_a_pin(self):
        # The parser lifts ``revision=main`` out of the model_args
        # string; the rule must flag it the same way it would flag the
        # top-level revision field.
        ids = rule_ids(scan_string(_record(
            model="org/model",
            revision=_DELETE,
            model_args="pretrained=org/model,revision=main",
        )))
        self.assertIn("EVAL-002", ids)


class Eval003LimitWithResults(unittest.TestCase):
    def test_limit_50_with_results(self):
        ids = rule_ids(scan_string(_record(limit=50)))
        self.assertIn("EVAL-003", ids)

    def test_limit_null_does_not_fire(self):
        ids = rule_ids(scan_string(_record(limit=None)))
        self.assertNotIn("EVAL-003", ids)


class Eval004FewshotInconsistency(unittest.TestCase):
    def test_differing_fewshot_across_configs(self):
        ids = rule_ids(scan_string(_record(
            configs={
                "mmlu_college_physics": {"num_fewshot": 5},
                "boolq": {"num_fewshot": 0},
            },
            results={
                "mmlu_college_physics": {"acc": 0.6},
                "boolq": {"acc": 0.7},
            },
        )))
        self.assertIn("EVAL-004", ids)


class Eval005NoSeed(unittest.TestCase):
    def test_record_without_any_seed(self):
        ids = rule_ids(scan_string(_record(seed=_DELETE)))
        self.assertIn("EVAL-005", ids)

    def test_null_seed_fires_as_no_seed(self):
        # A JSON ``null`` seed is indistinguishable from "no seed was set"
        # for reproducibility purposes; EVAL-005 must fire.
        ids = rule_ids(scan_string(_record(seed=None)))
        self.assertIn("EVAL-005", ids)

    def test_empty_string_seed_fires_as_no_seed(self):
        ids = rule_ids(scan_string(_record(seed="")))
        self.assertIn("EVAL-005", ids)

    def test_whitespace_only_seed_fires_as_no_seed(self):
        ids = rule_ids(scan_string(_record(seed="   ")))
        self.assertIn("EVAL-005", ids)

    def test_zero_seed_does_not_fire(self):
        # 0 is a legitimate seed value and must not be mistaken for null.
        ids = rule_ids(scan_string(_record(seed=0)))
        self.assertNotIn("EVAL-005", ids)

    def test_null_seed_in_config_block_fires(self):
        r = json.loads(_record(seed=_DELETE))
        r["config"] = {"seed": None}
        ids = rule_ids(scan_string(json.dumps(r)))
        self.assertIn("EVAL-005", ids)

    def test_one_null_but_another_valid_does_not_fire(self):
        # If any seed slot carries a usable value the rule is satisfied.
        r = json.loads(_record(seed=None))
        r["random_seed"] = 42
        ids = rule_ids(scan_string(json.dumps(r)))
        self.assertNotIn("EVAL-005", ids)


class Eval006ScalarSeedInTupleSlot(unittest.TestCase):
    def test_seeds_as_scalar_fires(self):
        r = json.loads(_record())
        r["seeds"] = 1234
        ids = rule_ids(scan_string(json.dumps(r)))
        self.assertIn("EVAL-006", ids)


class Eval007SilentSamplingDrop(unittest.TestCase):
    def test_top_k_declared_but_absent_from_requests(self):
        r = json.loads(_record())
        r["sampling_params"] = {"top_k": 50, "temperature": 0.7}
        r["requests"] = [{"gen_kwargs": {"temperature": 0.7}}]
        ids = rule_ids(scan_string(json.dumps(r)))
        self.assertIn("EVAL-007", ids)

    def test_no_requests_block_does_not_fire(self):
        r = json.loads(_record())
        r["sampling_params"] = {"top_k": 50}
        # No requests array -> no evidence of silence.
        ids = rule_ids(scan_string(json.dumps(r)))
        self.assertNotIn("EVAL-007", ids)


class Eval008DuplicateTask(unittest.TestCase):
    def test_single_record_cannot_have_duplicate_keys_in_results(self):
        # JSON parsers normalize duplicates; the rule is defensible on
        # a JSONL stream. Build a two-record JSONL body.
        rec_a = json.loads(_record())
        rec_a["results"] = {"boolq": {"acc": 0.7}}
        rec_b = json.loads(_record())
        rec_b["results"] = {"boolq": {"acc": 0.9}}
        body = json.dumps(rec_a) + "\n" + json.dumps(rec_b)
        # Each record on its own doesn't duplicate; EVAL-008 is a
        # per-record check for duplicates within one record's results
        # (impossible via dict), so we instead cover the structural
        # invariant: a dict-based results map cannot carry duplicates.
        ids = rule_ids(scan_string(body))
        self.assertNotIn("EVAL-008", ids)


class Eval009FutureTimestamp(unittest.TestCase):
    def test_year_2099(self):
        ids = rule_ids(scan_string(_record(
            timestamp="2099-01-01T00:00:00Z")))
        self.assertIn("EVAL-009", ids)


class Eval010BootstrapZeroWithCi(unittest.TestCase):
    def test_bootstrap_iters_zero_and_stderr_present(self):
        ids = rule_ids(scan_string(_record(
            bootstrap_iters=0,
            results={"mmlu_college_physics": {"acc": 0.6,
                                               "acc_stderr": 0.01}},
        )))
        self.assertIn("EVAL-010", ids)


class Eval011NSamplesNonpositive(unittest.TestCase):
    def test_zero_n_samples(self):
        ids = rule_ids(scan_string(_record(
            results={"mmlu_college_physics": {"acc": 0.6, "n_samples": 0}},
        ), Options(include_info=True)))
        self.assertIn("EVAL-011", ids)


class Eval012DeclaredTasksTruncated(unittest.TestCase):
    def test_three_declared_two_reported(self):
        ids = rule_ids(scan_string(_record(
            tasks=["a", "b", "c"],
            results={"a": {"acc": 0.5}, "b": {"acc": 0.6}},
        )))
        self.assertIn("EVAL-012", ids)


class Eval013EnableThinkingOnMc(unittest.TestCase):
    def test_mmlu_plus_enable_thinking(self):
        ids = rule_ids(scan_string(_record(
            enable_thinking=True,
            results={"mmlu_physics_mc": {"acc": 0.6}},
        )))
        self.assertIn("EVAL-013", ids)


class Eval014ErrorButScore(unittest.TestCase):
    def test_score_plus_error_on_same_task(self):
        ids = rule_ids(scan_string(_record(
            results={"mmlu_college_physics": {
                "acc": 0.6,
                "error": "backend 500",
            }},
        )))
        self.assertIn("EVAL-014", ids)


class Eval015NoHarnessGit(unittest.TestCase):
    def test_missing_git_hash(self):
        ids = rule_ids(scan_string(_record(git_hash=_DELETE),
                                   Options(include_info=True)))
        self.assertIn("EVAL-015", ids)


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
