"""evalrunlint - offline linter for evaluation-harness result files.

Reads a results JSON or JSONL file produced by lm-eval-harness, EvalPlus,
LightEval or any similar harness and reports shape defects that break
comparability or reproducibility - unpinned model identifiers, missing
seeds, partial runs reported as full, inconsistent few-shot counts,
sampling params declared but not forwarded to the backend, duplicate
tasks with differing scores, future timestamps, confidence intervals
without bootstrap iterations, and more.

Zero network. Zero third-party dependencies. Python 3.9+.

A clean run means the record is internally consistent and complete
against a named checklist. It never means the reported numbers are
correct, or that the model would produce them on re-run.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .rules import REGISTRY, Check, Rule
from .types import Finding, Options, ScanResult, Severity, Verdict

# repro-lab/docs/CONVENTIONS.md names the shared rule table ALL_RULES.
ALL_RULES = REGISTRY

__all__ = [
    "__version__",
    "Severity",
    "Verdict",
    "Finding",
    "ScanResult",
    "Options",
    "ALL_RULES",
    "Rule",
    "REGISTRY",
    "Check",
]
