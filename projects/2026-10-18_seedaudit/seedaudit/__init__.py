"""seedaudit - AST-based audit of RNG calls without a seed in scope.

Reads Python source and reports every call to a known random-number
generator function that occurs without a seeding call or a
``random_state``/``seed``/``generator`` keyword argument in the enclosing
scope. Also flags reseed-mid-function and seed-defined-but-never-called
patterns.

Zero network. Zero third-party dependencies. Python 3.9+.
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
