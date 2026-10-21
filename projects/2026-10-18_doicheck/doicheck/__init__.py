"""doicheck - offline linter for scholarly identifiers and BibTeX hygiene.

Validates DOI, arXiv, ORCID, and ISBN identifiers against their public
format and checksum rules, and lints BibTeX entries for the shape defects
that cause reproducibility failures at the citation layer (missing required
fields, future years, empty-valued fields, duplicate keys, unbalanced braces).

Zero network. Zero third-party dependencies. Python 3.9+.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .rules import REGISTRY, Check, Rule
from .types import Finding, Options, ScanResult, Severity, Verdict

# The lab's shared package surface (repro-lab/docs/CONVENTIONS.md) names
# the rule table ALL_RULES and the rule type Rule. The internal spelling
# is REGISTRY / Check; ALL_RULES is a stable alias.
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
