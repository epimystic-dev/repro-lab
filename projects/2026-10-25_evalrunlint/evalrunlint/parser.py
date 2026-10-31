"""Shape-level parser for evaluation-harness result files.

The three main public harness formats share a core shape (a results map
keyed by task name, a config block, a model identifier string, optional
few-shot and sampling blocks) but spell field names differently. This
module reads what is on disk and lifts it into a single normalized record
the rule registry walks. It never contacts any registry.

Supported inputs:

  - single JSON file (lm-eval-harness ``results.json``, EvalPlus
    ``results.json``, LightEval ``details.json``);
  - JSONL file where each line is one record (``results.jsonl``,
    per-task result files).

The shape is intentionally permissive: anything the parser cannot
classify is still returned as a record with raw payload, and rules then
fire on whatever fields they can locate.

Public spec sources paraphrased (never vendored):

  - lm-evaluation-harness README and configuration section, github
    EleutherAI/lm-evaluation-harness, including the ``results``,
    ``configs``, ``model``, ``model_args``, ``num_fewshot``, ``limit``,
    ``bootstrap_iters``, ``seed`` and ``git_hash`` keys.
  - EvalPlus README and the ``results.json`` schema it writes.
  - LightEval configuration docs for ``sampling_params`` (``top_k``,
    ``min_p``, ``presence_penalty`` et al).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# Field aliases: harnesses spell the same concept several ways. We walk
# the record and promote whichever one is present. Order matters: the
# first match wins.

_MODEL_FIELDS: Tuple[str, ...] = (
    "model", "model_name", "model_id", "pretrained",
)

_MODEL_ARGS_FIELDS: Tuple[str, ...] = (
    "model_args", "model_kwargs",
)

_REVISION_FIELDS: Tuple[str, ...] = (
    "revision", "model_sha", "commit", "commit_hash", "revision_hash",
    "digest", "sha",
)

_SEED_FIELDS: Tuple[str, ...] = (
    "seed", "random_seed", "rng_seed", "numpy_seed", "numpy_random_seed",
    "torch_seed", "torch_random_seed", "fewshot_random_seed",
    # Plural / tuple-expecting slots. EVAL-006 inspects their shape.
    "seeds", "random_seeds", "rng_seeds", "numpy_random_seeds",
)

_SAMPLING_FIELDS: Tuple[str, ...] = (
    "temperature", "top_k", "top_p", "min_p", "typical_p",
    "repetition_penalty", "presence_penalty", "frequency_penalty",
    "num_beams", "do_sample", "max_new_tokens", "max_tokens",
)

_FEWSHOT_FIELDS: Tuple[str, ...] = (
    "num_fewshot", "fewshot", "n_shot", "n_shots", "num_shots",
)

_HARNESS_GIT_FIELDS: Tuple[str, ...] = (
    "git_hash", "harness_git_hash", "harness_revision",
    "lm_eval_harness_version", "harness_version",
)

_ERROR_FIELDS: Tuple[str, ...] = (
    "error", "traceback", "exception", "stack_trace",
)

_TIMESTAMP_FIELDS: Tuple[str, ...] = (
    "timestamp", "date", "datetime", "end_time", "start_time",
    "created_at",
)


@dataclass
class HarnessRecord:
    """One normalized record extracted from a result file.

    Multiple records per file are possible (JSONL, or a single JSON
    that packs several task-level records under one envelope).
    """

    source_line: int = 0
    model: Optional[str] = None
    model_args_raw: Optional[Any] = None
    model_args_dict: Dict[str, str] = field(default_factory=dict)
    revision: Optional[str] = None
    seed_fields: Dict[str, Any] = field(default_factory=dict)
    sampling_declared: Dict[str, Any] = field(default_factory=dict)
    fewshot_values: Dict[str, int] = field(default_factory=dict)
    tasks_declared: List[str] = field(default_factory=list)
    tasks_reported: List[str] = field(default_factory=list)
    results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    limit: Any = None
    bootstrap_iters: Any = None
    enable_thinking: Any = None
    harness_git: Optional[str] = None
    error_fields_present: List[Tuple[str, str]] = field(default_factory=list)
    timestamp_fields: Dict[str, Any] = field(default_factory=dict)
    requests_sampling_seen: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


def _first_present(d: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[str]:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return k
    return None


def _parse_model_args_string(s: str) -> Dict[str, str]:
    """Parse the lm-eval-harness ``k=v,k=v`` model-args string.

    Values that contain ``=`` are preserved; empty values are kept as
    empty strings so a rule can see them.
    """
    out: Dict[str, str] = {}
    if not isinstance(s, str) or not s:
        return out
    for piece in s.split(","):
        if not piece.strip():
            continue
        if "=" in piece:
            k, _, v = piece.partition("=")
            out[k.strip()] = v.strip()
        else:
            out[piece.strip()] = ""
    return out


def _coerce_model_args(obj: Any) -> Dict[str, str]:
    if isinstance(obj, str):
        return _parse_model_args_string(obj)
    if isinstance(obj, dict):
        return {str(k): str(v) for k, v in obj.items()}
    return {}


def _extract_revision(record: Dict[str, Any],
                      model_args: Dict[str, str]) -> Optional[str]:
    for k in _REVISION_FIELDS:
        if k in record and record[k]:
            return str(record[k])
        if k in model_args and model_args[k]:
            return str(model_args[k])
    for k in ("model_sha", "model_commit", "model_revision"):
        if k in record and record[k]:
            return str(record[k])
    cfg = record.get("config") or {}
    if isinstance(cfg, dict):
        for k in _REVISION_FIELDS:
            if k in cfg and cfg[k]:
                return str(cfg[k])
    return None


def _is_present_seed(v: Any) -> bool:
    """A seed field counts as "present" only if it carries a usable value.

    ``null`` and the empty string are treated as absent: they are
    indistinguishable from "the seed was not set" when it comes to
    re-running the experiment. This matches the convention used by
    ``_first_present`` for model fields. ``0`` is a valid seed value.
    """
    if v is None:
        return False
    if isinstance(v, str) and v.strip() == "":
        return False
    return True


def _collect_seeds(record: Dict[str, Any],
                   model_args: Dict[str, str]) -> Dict[str, Any]:
    seeds: Dict[str, Any] = {}
    for k in _SEED_FIELDS:
        if k in record and _is_present_seed(record[k]):
            seeds[k] = record[k]
        if k in model_args and _is_present_seed(model_args[k]):
            seeds[k] = model_args[k]
    cfg = record.get("config") or {}
    if isinstance(cfg, dict):
        for k in _SEED_FIELDS:
            if k in cfg and _is_present_seed(cfg[k]):
                seeds[k] = cfg[k]
    gk = record.get("gen_kwargs")
    if isinstance(gk, dict):
        for k in _SEED_FIELDS:
            if k in gk and _is_present_seed(gk[k]):
                seeds[k] = gk[k]
    return seeds


def _collect_sampling(record: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in _SAMPLING_FIELDS:
        if k in record:
            out[k] = record[k]
    for parent in ("gen_kwargs", "sampling_params", "generation_config",
                   "config"):
        sub = record.get(parent)
        if isinstance(sub, dict):
            for k in _SAMPLING_FIELDS:
                if k in sub:
                    out[k] = sub[k]
    return out


def _collect_requests_sampling(record: Dict[str, Any]) -> Dict[str, Any]:
    """Walk any ``requests`` / ``samples`` list on the record and
    return the sampling params that *actually* appear on the recorded
    calls, so a rule can compare them against the declared config.
    """
    out: Dict[str, Any] = {}
    for key in ("requests", "samples", "generations"):
        lst = record.get(key)
        if isinstance(lst, list):
            for item in lst:
                if not isinstance(item, dict):
                    continue
                for inner in (item, item.get("gen_kwargs") or {},
                              item.get("sampling_params") or {}):
                    if not isinstance(inner, dict):
                        continue
                    for k in _SAMPLING_FIELDS:
                        if k in inner:
                            out[k] = inner[k]
    return out


def _collect_fewshot(record: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for k in _FEWSHOT_FIELDS:
        v = record.get(k)
        if isinstance(v, int):
            out[k] = v
    cfg = record.get("config") or {}
    if isinstance(cfg, dict):
        for k in _FEWSHOT_FIELDS:
            v = cfg.get(k)
            if isinstance(v, int):
                out["config." + k] = v
    cfgs = record.get("configs")
    if isinstance(cfgs, dict):
        for task_name, cfg in cfgs.items():
            if isinstance(cfg, dict):
                for k in _FEWSHOT_FIELDS:
                    v = cfg.get(k)
                    if isinstance(v, int):
                        out[str(task_name) + "." + k] = v
    return out


def _collect_results(record: Dict[str, Any]
                     ) -> Dict[str, Dict[str, Any]]:
    r = record.get("results")
    if isinstance(r, dict) and r:
        norm: Dict[str, Dict[str, Any]] = {}
        for k, v in r.items():
            if isinstance(v, dict):
                norm[str(k)] = v
            else:
                norm[str(k)] = {"value": v}
        return norm
    for alt in ("task_results", "scores", "metrics"):
        r = record.get(alt)
        if isinstance(r, dict) and r:
            norm = {}
            for k, v in r.items():
                if isinstance(v, dict):
                    norm[str(k)] = v
                else:
                    norm[str(k)] = {"value": v}
            return norm
    return {}


def _collect_tasks_declared(record: Dict[str, Any]) -> List[str]:
    for key in ("tasks", "task_list", "requested_tasks"):
        v = record.get(key)
        if isinstance(v, list) and all(isinstance(x, str) for x in v):
            return list(v)
    cfg = record.get("config") or {}
    if isinstance(cfg, dict):
        for key in ("tasks", "task_list", "requested_tasks"):
            v = cfg.get(key)
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                return list(v)
    cfgs = record.get("configs")
    if isinstance(cfgs, dict):
        return [str(k) for k in cfgs.keys()]
    return []


def _collect_timestamps(record: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in _TIMESTAMP_FIELDS:
        if k in record:
            out[k] = record[k]
    cfg = record.get("config") or {}
    if isinstance(cfg, dict):
        for k in _TIMESTAMP_FIELDS:
            if k in cfg:
                out[k] = cfg[k]
    return out


def _collect_errors(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    r = record.get("results") or {}
    if isinstance(r, dict):
        for task, body in r.items():
            if isinstance(body, dict):
                for ek in _ERROR_FIELDS:
                    if ek in body and body[ek]:
                        out.append((str(task), ek))
    for ek in _ERROR_FIELDS:
        if ek in record and record[ek]:
            out.append(("", ek))
    return out


def normalize_record(obj: Dict[str, Any], source_line: int = 0
                     ) -> HarnessRecord:
    rec = HarnessRecord(source_line=source_line, raw=obj)
    model_key = _first_present(obj, _MODEL_FIELDS)
    if model_key is not None:
        rec.model = str(obj[model_key])
    args_key = _first_present(obj, _MODEL_ARGS_FIELDS)
    if args_key is not None:
        rec.model_args_raw = obj[args_key]
        rec.model_args_dict = _coerce_model_args(obj[args_key])
    if rec.model is None:
        for k in ("pretrained", "model"):
            if k in rec.model_args_dict and rec.model_args_dict[k]:
                rec.model = rec.model_args_dict[k]
                break
    cfg = obj.get("config")
    if isinstance(cfg, dict):
        rec.config = cfg
        if rec.model is None:
            mk = _first_present(cfg, _MODEL_FIELDS)
            if mk is not None:
                rec.model = str(cfg[mk])
    rec.revision = _extract_revision(obj, rec.model_args_dict)
    rec.seed_fields = _collect_seeds(obj, rec.model_args_dict)
    rec.sampling_declared = _collect_sampling(obj)
    rec.requests_sampling_seen = _collect_requests_sampling(obj)
    rec.fewshot_values = _collect_fewshot(obj)
    rec.results = _collect_results(obj)
    rec.tasks_declared = _collect_tasks_declared(obj)
    rec.tasks_reported = list(rec.results.keys())
    for ek in ("limit",):
        if ek in obj:
            rec.limit = obj[ek]
        elif isinstance(cfg, dict) and ek in cfg:
            rec.limit = cfg[ek]
    for ek in ("bootstrap_iters",):
        if ek in obj:
            rec.bootstrap_iters = obj[ek]
        elif isinstance(cfg, dict) and ek in cfg:
            rec.bootstrap_iters = cfg[ek]
    for ek in ("enable_thinking",):
        if ek in obj:
            rec.enable_thinking = obj[ek]
        elif isinstance(cfg, dict) and ek in cfg:
            rec.enable_thinking = cfg[ek]
    gk = _first_present(obj, _HARNESS_GIT_FIELDS)
    if gk is not None:
        rec.harness_git = str(obj[gk])
    elif isinstance(cfg, dict):
        gk = _first_present(cfg, _HARNESS_GIT_FIELDS)
        if gk is not None:
            rec.harness_git = str(cfg[gk])
    rec.timestamp_fields = _collect_timestamps(obj)
    rec.error_fields_present = _collect_errors(obj)
    return rec


def parse_file(content: str) -> Tuple[List[HarnessRecord], Optional[str]]:
    """Parse a result file. Returns (records, error_or_None).

    Tries pure JSON first (one big envelope). If that fails, falls back
    to JSONL. If neither parse succeeds, returns an error string.
    """
    content_stripped = content.lstrip()
    err: Optional[str] = None
    if content_stripped.startswith("{") or content_stripped.startswith("["):
        try:
            obj = json.loads(content)
        except json.JSONDecodeError as e:
            err = "invalid JSON: " + str(e)
        else:
            if isinstance(obj, dict):
                return [normalize_record(obj, source_line=1)], None
            if isinstance(obj, list):
                return (
                    [normalize_record(x, source_line=i + 1)
                     for i, x in enumerate(obj) if isinstance(x, dict)],
                    None,
                )
            return [], "top-level JSON is neither object nor array"
    out: List[HarnessRecord] = []
    for i, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            if err is None:
                err = "line " + str(i) + ": not valid JSON"
            continue
        if isinstance(obj, dict):
            out.append(normalize_record(obj, source_line=i))
    if not out:
        return [], err or "no JSON records found"
    return out, None


__all__ = [
    "HarnessRecord",
    "normalize_record",
    "parse_file",
]
