"""Rule registry for evalrunlint.

Fifteen rules spanning model-pin, seed-pin, few-shot, limit, sampling,
tasks-declared-vs-reported, timestamps, bootstrap, enable-thinking, and
harness-identity defects. Every rule cites a public source. Rule IDs use
the ``EVAL-`` prefix.

A clean run means the record is internally consistent and complete
against the named checklist. It never means the reported numbers are
correct, or that the model would produce them on re-run.

Public spec sources paraphrased (never vendored):

  - lm-evaluation-harness README, configuration docs, and the v0.4.13
    release notes documenting the few-shot leakage fix, the scalar-seed
    normalization fix, the ``enable_thinking`` config validation, and
    the ``gen_prefix`` resolution fix.
  - EvalPlus README on ``results.json`` structure.
  - LightEval configuration docs on ``sampling_params`` and the
    reported silent-drop of ``top_k`` / ``min_p`` / ``presence_penalty``.
  - PromptLayer 2026 "Why LLM Evaluation Results Aren't Reproducible"
    guide for the comparability checklist (model pin, seed pin, limit,
    few-shot count, sampling).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from .parser import HarnessRecord, parse_file
from .types import Finding, Options, Severity


Check = Callable[[List[HarnessRecord], Options, str], List[Finding]]


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    title: str
    description: str
    citation: str
    check: Check


# Branch / symbolic refs that move. The Hugging Face Hub revision docs
# are explicit that a branch pointer such as ``main`` is resolved to
# whatever commit it currently points at; only a commit sha (or an
# immutable tag) will reproduce the recorded run later.
_MOVABLE_REF_NAMES = frozenset(("main", "master", "head"))


def _is_movable_ref(name: object) -> bool:
    if not isinstance(name, str):
        return False
    return name.strip().lower() in _MOVABLE_REF_NAMES


# A loose regex-free check: a model string "looks pinned" if it has an
# explicit revision/sha/commit either as a field or as a suffix after
# ``@`` or ``#``. A branch-name revision (``main``, ``master``, ``HEAD``)
# is treated as unpinned on either path - the two code paths must agree
# so that revision="main" and model="org/m@main" are both flagged.
def _looks_pinned(model: str, revision: object) -> bool:
    if revision not in (None, "") and not _is_movable_ref(revision):
        return True
    if "@" in (model or "") or "#" in (model or ""):
        tail = model.split("@", 1)[-1].split("#", 1)[-1]
        return bool(tail) and not _is_movable_ref(tail)
    return False


# A sampling param "looks silently dropped" if it is declared in the
# config but is absent from every recorded request. We only fire when
# the record actually has a recorded requests list to compare against -
# otherwise we have no evidence of silence.
_SILENT_DROP_CANDIDATES = ("top_k", "min_p", "presence_penalty",
                           "frequency_penalty", "typical_p")


def _multiple_choice_task(name: str) -> bool:
    n = name.lower()
    return any(tok in n for tok in (
        "mmlu", "arc", "hellaswag", "winogrande", "piqa", "openbookqa",
        "boolq", "truthfulqa_mc", "mc1", "mc2", "logiqa",
    ))


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _no_model(records, options, path):
    out: List[Finding] = []
    for rec in records:
        if not rec.model and not rec.model_args_dict:
            out.append(Finding(
                rule_id="EVAL-001",
                severity=Severity.HIGH,
                message="result file has no model identifier",
                subject="(record)",
                line=rec.source_line,
                path=path,
                hint="add a 'model' or 'model_args' field so a reader can tell which model was run",
                citation="lm-eval-harness README; LightEval config docs",
            ))
    return out


def _unpinned_model(records, options, path):
    out: List[Finding] = []
    for rec in records:
        if rec.model and not _looks_pinned(rec.model, rec.revision):
            out.append(Finding(
                rule_id="EVAL-002",
                severity=Severity.HIGH,
                message=("model identifier is not pinned to an immutable"
                         " revision"),
                subject=rec.model,
                line=rec.source_line,
                path=path,
                hint=("add a revision/sha/commit field or '@<sha>' suffix;"
                      " a tag or branch moves"),
                citation=("Hugging Face Hub model-revision docs;"
                          " lm-eval-harness model_args"),
            ))
    return out


def _limit_set_with_results(records, options, path):
    out: List[Finding] = []
    for rec in records:
        lim = rec.limit
        if lim in (None, False, 0):
            continue
        if isinstance(lim, (int, float)) and lim > 0 and rec.results:
            out.append(Finding(
                rule_id="EVAL-003",
                severity=Severity.HIGH,
                message=("result reported with limit=" + str(lim) +
                         "; partial run"),
                subject=",".join(sorted(rec.results.keys())[:3]) or "(tasks)",
                line=rec.source_line,
                path=path,
                hint=("rerun without --limit, or add a 'partial: true'"
                      " marker to the record"),
                citation="lm-eval-harness --limit flag docs",
            ))
    return out


def _inconsistent_fewshot(records, options, path):
    out: List[Finding] = []
    for rec in records:
        values = list(rec.fewshot_values.values())
        if len(set(values)) > 1:
            spread = sorted(set(values))
            out.append(Finding(
                rule_id="EVAL-004",
                severity=Severity.HIGH,
                message=("few-shot count differs across tasks: " +
                         ",".join(str(v) for v in spread)),
                subject="num_fewshot",
                line=rec.source_line,
                path=path,
                hint=("report one task per record, or declare the few-shot"
                      " count per task"),
                citation="lm-eval-harness per-task fewshot config",
            ))
    return out


def _no_seed(records, options, path):
    out: List[Finding] = []
    for rec in records:
        if not rec.seed_fields:
            out.append(Finding(
                rule_id="EVAL-005",
                severity=Severity.MEDIUM,
                message=("no seed field present anywhere on the record"),
                subject="(record)",
                line=rec.source_line,
                path=path,
                hint=("set 'seed', 'random_seed', or an equivalent so the"
                      " run is reproducible"),
                citation=("lm-eval-harness seed / random_seed /"
                          " fewshot_random_seed"),
            ))
    return out


# EVAL-006: lm-eval-harness v0.4.13 release-note bug: a scalar seed read
# from a config file where a 4-tuple was required silently normalized to
# a non-equivalent state. We flag any field named *_seeds (plural, or
# "seeds" alone) whose value is a scalar.
def _scalar_seed_in_tuple_slot(records, options, path):
    out: List[Finding] = []
    for rec in records:
        for k, v in rec.seed_fields.items():
            looks_plural = k.endswith("seeds") or k == "seeds"
            if looks_plural and isinstance(v, (int, float)):
                out.append(Finding(
                    rule_id="EVAL-006",
                    severity=Severity.HIGH,
                    message=("field '" + k +
                             "' is a scalar; expected a list/tuple"),
                    subject=k + "=" + str(v),
                    line=rec.source_line,
                    path=path,
                    hint=("use a list like [seed_a, seed_b, seed_c, seed_d]"
                          " instead of a single int"),
                    citation=("lm-evaluation-harness v0.4.13 release notes"
                              " on scalar seed normalization"),
                ))
    return out


# EVAL-007: declared-but-silently-dropped sampling params.
def _silent_sampling_drop(records, options, path):
    out: List[Finding] = []
    for rec in records:
        if not rec.requests_sampling_seen:
            continue
        for k in _SILENT_DROP_CANDIDATES:
            if k in rec.sampling_declared and k not in rec.requests_sampling_seen:
                out.append(Finding(
                    rule_id="EVAL-007",
                    severity=Severity.HIGH,
                    message=("sampling param '" + k +
                             "' declared in config but absent from recorded"
                             " requests"),
                    subject=k + "=" + str(rec.sampling_declared[k]),
                    line=rec.source_line,
                    path=path,
                    hint=("verify the backend accepts this parameter and"
                          " that the harness forwards it; LightEval reported"
                          " a silent-drop class for exactly these fields"),
                    citation=("LightEval sampling-params docs;"
                              " huggingface/lighteval issue tracker"),
                ))
    return out


def _duplicate_task_differing_scores(records, options, path):
    out: List[Finding] = []
    for rec in records:
        seen: Dict[str, object] = {}
        for task_name, body in rec.results.items():
            if not isinstance(body, dict):
                continue
            score = None
            for mk in ("acc", "accuracy", "score", "exact_match",
                       "pass@1", "value"):
                if mk in body:
                    score = body[mk]
                    break
            if task_name in seen and seen[task_name] != score:
                out.append(Finding(
                    rule_id="EVAL-008",
                    severity=Severity.HIGH,
                    message=("task '" + task_name +
                             "' appears twice with differing scores"),
                    subject=task_name,
                    line=rec.source_line,
                    path=path,
                    hint=("de-duplicate before reporting"),
                    citation=("lm-eval-harness task-registry duplicate"
                              " detection"),
                ))
            seen[task_name] = score
    return out


def _future_timestamp(records, options, path):
    out: List[Finding] = []
    for rec in records:
        for k, v in rec.timestamp_fields.items():
            if not isinstance(v, str):
                continue
            # ISO-like year prefix: four digits at the start.
            if len(v) >= 4 and v[:4].isdigit():
                yr = int(v[:4])
                if yr > options.current_year:
                    out.append(Finding(
                        rule_id="EVAL-009",
                        severity=Severity.MEDIUM,
                        message=("timestamp field '" + k + "' year is in"
                                 " the future (" + str(yr) + ")"),
                        subject=k + "=" + v,
                        line=rec.source_line,
                        path=path,
                        hint=("set --current-year to override; otherwise"
                              " a future date indicates clock skew or a"
                              " fabricated record"),
                        citation="PromptLayer 2026 reproducibility checklist",
                    ))
    return out


def _bootstrap_zero_but_ci_present(records, options, path):
    out: List[Finding] = []
    for rec in records:
        bi = rec.bootstrap_iters
        if bi in (None, 0, "0", False):
            for task_name, body in rec.results.items():
                if not isinstance(body, dict):
                    continue
                for ci_key in ("stderr", "acc_stderr", "ci_low", "ci_high",
                               "confidence_interval"):
                    if ci_key in body and body[ci_key] not in (None, ""):
                        out.append(Finding(
                            rule_id="EVAL-010",
                            severity=Severity.MEDIUM,
                            message=("confidence-interval field '" + ci_key
                                     + "' present but bootstrap_iters is"
                                     " zero/missing on task '" + task_name
                                     + "'"),
                            subject=task_name + "." + ci_key,
                            line=rec.source_line,
                            path=path,
                            hint=("set bootstrap_iters > 0 to make the CI"
                                  " meaningful"),
                            citation=("lm-eval-harness bootstrap_iters"
                                      " configuration docs"),
                        ))
    return out


def _n_samples_nonpositive(records, options, path):
    out: List[Finding] = []
    for rec in records:
        for task_name, body in rec.results.items():
            if not isinstance(body, dict):
                continue
            for k in ("n_samples", "num_samples", "n", "num"):
                if k in body and isinstance(body[k], (int, float)):
                    if body[k] <= 0:
                        out.append(Finding(
                            rule_id="EVAL-011",
                            severity=Severity.INFO,
                            message=("task '" + task_name + "' reports a"
                                     " score but '" + k + "' is"
                                     " non-positive"),
                            subject=task_name + "." + k + "="
                                    + str(body[k]),
                            line=rec.source_line,
                            path=path,
                            hint=("verify the task was actually run on at"
                                  " least one sample"),
                            citation=("lm-eval-harness per-task n_samples"
                                      " recording"),
                        ))
    return out


def _declared_tasks_truncated(records, options, path):
    out: List[Finding] = []
    for rec in records:
        if not rec.tasks_declared or not rec.results:
            continue
        reported = set(rec.tasks_reported)
        missing = [t for t in rec.tasks_declared if t not in reported]
        if missing:
            out.append(Finding(
                rule_id="EVAL-012",
                severity=Severity.HIGH,
                message=("declared " + str(len(rec.tasks_declared)) +
                         " tasks, reported " + str(len(reported)) +
                         "; missing: " + ",".join(sorted(missing)[:3])),
                subject=",".join(sorted(missing)[:3]),
                line=rec.source_line,
                path=path,
                hint=("rerun the missing tasks, or remove them from the"
                      " declared list before publishing"),
                citation="lm-eval-harness task-selection docs",
            ))
    return out


def _enable_thinking_on_mc(records, options, path):
    out: List[Finding] = []
    for rec in records:
        et = rec.enable_thinking
        if et in (None, False, "false", "False", 0):
            continue
        for task_name in rec.tasks_reported:
            if _multiple_choice_task(task_name):
                out.append(Finding(
                    rule_id="EVAL-013",
                    severity=Severity.MEDIUM,
                    message=("enable_thinking=True combined with"
                             " multiple-choice task '" + task_name + "'"),
                    subject="enable_thinking",
                    line=rec.source_line,
                    path=path,
                    hint=("v0.4.13 of lm-evaluation-harness disallows"
                          " enable_thinking for multiple_choice and"
                          " loglikelihood tasks; set it False or exclude"
                          " these tasks"),
                    citation=("lm-evaluation-harness v0.4.13 release notes"
                              " on enable_thinking validation"),
                ))
    return out


def _error_but_score(records, options, path):
    out: List[Finding] = []
    for rec in records:
        if not rec.error_fields_present:
            continue
        for task_name, body in rec.results.items():
            if not isinstance(body, dict):
                continue
            has_score = False
            for mk in ("acc", "accuracy", "score", "exact_match",
                       "pass@1", "value"):
                if mk in body and isinstance(body[mk], (int, float)):
                    has_score = True
                    break
            if has_score:
                task_errors = [k for (t, k) in rec.error_fields_present
                               if t == task_name or t == ""]
                if task_errors:
                    out.append(Finding(
                        rule_id="EVAL-014",
                        severity=Severity.HIGH,
                        message=("task '" + task_name + "' reports a"
                                 " score but has an error field (" +
                                 ",".join(sorted(set(task_errors))) + ")"),
                        subject=task_name,
                        line=rec.source_line,
                        path=path,
                        hint=("remove the score or remove the error field;"
                              " a reader cannot tell which is authoritative"),
                        citation=("lm-eval-harness task-level error"
                                  " recording"),
                    ))
    return out


def _no_harness_git(records, options, path):
    out: List[Finding] = []
    for rec in records:
        if not rec.harness_git:
            out.append(Finding(
                rule_id="EVAL-015",
                severity=Severity.INFO,
                message=("no harness git-hash / version recorded on the"
                         " record"),
                subject="(record)",
                line=rec.source_line,
                path=path,
                hint=("set git_hash or harness_version so a reviewer can"
                      " reproduce under the same harness code"),
                citation=("lm-eval-harness --log-samples / --log-info"
                          " git_hash field"),
            ))
    return out


REGISTRY: List[Rule] = [
    Rule("EVAL-001", Severity.HIGH,
         "no model identifier",
         "result file has no model name or model_args",
         "lm-eval-harness README",
         _no_model),
    Rule("EVAL-002", Severity.HIGH,
         "unpinned model",
         "model identifier has no immutable revision or sha",
         "Hugging Face Hub revision docs",
         _unpinned_model),
    Rule("EVAL-003", Severity.HIGH,
         "limit set but result reported",
         "a partial run is being presented as if it were a full one",
         "lm-eval-harness --limit flag docs",
         _limit_set_with_results),
    Rule("EVAL-004", Severity.HIGH,
         "inconsistent few-shot",
         "num_fewshot differs across tasks on the same record",
         "lm-eval-harness per-task fewshot config",
         _inconsistent_fewshot),
    Rule("EVAL-005", Severity.MEDIUM,
         "no seed",
         "no seed, random_seed, numpy_seed, torch_seed, or equivalent",
         "lm-eval-harness seed / random_seed",
         _no_seed),
    Rule("EVAL-006", Severity.HIGH,
         "scalar seed in a tuple-expecting slot",
         "field named *_seeds carries a scalar value",
         "lm-evaluation-harness v0.4.13 release notes",
         _scalar_seed_in_tuple_slot),
    Rule("EVAL-007", Severity.HIGH,
         "silent sampling-param drop",
         "a sampling param is declared in config but absent from recorded"
         " requests",
         "huggingface/lighteval issue tracker on silent-drop sampling",
         _silent_sampling_drop),
    Rule("EVAL-008", Severity.HIGH,
         "duplicate task with differing scores",
         "the same task key appears more than once with different scores",
         "lm-eval-harness task-registry duplicate detection",
         _duplicate_task_differing_scores),
    Rule("EVAL-009", Severity.MEDIUM,
         "future timestamp",
         "a timestamp field has a year beyond --current-year",
         "PromptLayer 2026 reproducibility checklist",
         _future_timestamp),
    Rule("EVAL-010", Severity.MEDIUM,
         "confidence interval without bootstrap",
         "stderr / ci_* fields are present but bootstrap_iters is zero or"
         " missing",
         "lm-eval-harness bootstrap_iters configuration docs",
         _bootstrap_zero_but_ci_present),
    Rule("EVAL-011", Severity.INFO,
         "non-positive sample count",
         "task reports a score but n_samples is zero or negative",
         "lm-eval-harness per-task n_samples recording",
         _n_samples_nonpositive),
    Rule("EVAL-012", Severity.HIGH,
         "declared tasks truncated",
         "configs declares N tasks but results reports fewer",
         "lm-eval-harness task-selection docs",
         _declared_tasks_truncated),
    Rule("EVAL-013", Severity.MEDIUM,
         "enable_thinking on multiple-choice",
         "enable_thinking True combined with a multiple-choice task",
         "lm-evaluation-harness v0.4.13 release notes",
         _enable_thinking_on_mc),
    Rule("EVAL-014", Severity.HIGH,
         "score reported alongside an error",
         "task has a score field and an error / traceback field",
         "lm-eval-harness task-level error recording",
         _error_but_score),
    Rule("EVAL-015", Severity.INFO,
         "no harness git hash",
         "no git_hash / harness_version recorded on the record",
         "lm-eval-harness --log-samples git_hash field",
         _no_harness_git),
]


def run_all(content: str, path: str, options: Options
            ) -> List[Finding]:
    records, err = parse_file(content)
    out: List[Finding] = []
    if err is not None and not records:
        out.append(Finding(
            rule_id="EVAL-000",
            severity=Severity.HIGH,
            message="could not parse result file: " + err,
            subject="",
            line=0,
            path=path,
            hint="pass a JSON or JSONL evaluation-harness result file",
            citation="",
        ))
        return out
    for rule in REGISTRY:
        if not options.rule_enabled(rule.id):
            continue
        if rule.severity is Severity.INFO and not (
                options.include_info or options.strict):
            continue
        out.extend(rule.check(records, options, path))
    return out


__all__ = ["REGISTRY", "Rule", "Check", "run_all"]
