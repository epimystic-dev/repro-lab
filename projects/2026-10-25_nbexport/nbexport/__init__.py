"""nbexport - lint Jupyter notebooks for execution-order defects and
emit a .py script in linear or recorded execution order.

Reads a .ipynb file (nbformat v4) and reports the defects that make a
notebook silently non-reproducible: out-of-order execution, duplicate
execution counts, never-run cells wedged between executed ones, cells
that were cleared after execution, line magics or shell commands that
plain-Python replay cannot handle, imports in a cell that was executed
after a cell that already used them, missing kernelspec metadata, and
non-Python language metadata.

Zero network. Zero third-party dependencies. Python 3.9+.

A clean run means the notebook's execution record is internally
consistent against the named checklist. It does **not** guarantee a
top-to-bottom execution would succeed, or produce the recorded outputs.
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
