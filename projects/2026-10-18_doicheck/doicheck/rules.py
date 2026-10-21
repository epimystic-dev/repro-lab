"""Rule registry for doicheck.

Fifteen rules spanning identifier format/checksum validation and BibTeX
hygiene. Every rule cites the public spec it implements. Rule IDs use the
``DOI-`` prefix. The lab-wide shared surface exposes this list as
``ALL_RULES``.

A clean run means the record is well-formed and internally consistent
against the named checklist. It never means the identifiers resolve or
that the cited work exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .bibtex import BibEntry, REQUIRED_FIELDS, parse_bibtex
from .identifiers import (
    validate_arxiv_id,
    validate_doi,
    validate_isbn,
    validate_orcid,
)
from .types import Finding, Options, Severity


# A check takes a parsed context dict and emits findings. Context carries
# everything needed by every rule - rules remain pure functions.
Check = Callable[[dict, Options], List[Finding]]


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    title: str
    description: str
    citation: str
    check: Check


# ---------------------------------------------------------------------------
# Identifier rules - fire on standalone identifier lines or on BibTeX
# fields that carry an identifier.
# ---------------------------------------------------------------------------

_DOI_LINE_RE = re.compile(r"\b\d+\.\d+(?:\.\d+)*/[^\s\"'{}<>]+")
_ARXIV_LINE_RE = re.compile(
    r"\barXiv:\s*([a-z\-\.]+/\d{7}(?:v\d+)?|\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)
_ORCID_LINE_RE = re.compile(
    r"(?:https?://orcid\.org/|orcid\.org/|\bORCID[:\s]+)"
    r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])",
    re.IGNORECASE,
)
_ISBN_LINE_RE = re.compile(
    r"\bISBN(?:-1[03])?[:\s]+([\dXx\- ]{10,20})"
)


def _check_doi_lines(ctx: dict, options: Options) -> List[Finding]:
    findings: List[Finding] = []
    for lineno, line in ctx["lines"]:
        for m in _DOI_LINE_RE.finditer(line):
            cand = m.group(0)
            r = validate_doi(cand)
            if r.ok:
                continue
            sev = Severity.HIGH
            rule_id = {
                "no-slash": "DOI-002",
                "empty-suffix": "DOI-002",
                "bad-prefix": "DOI-001",
                "forbidden-char": "DOI-003",
            }.get(r.reason, "DOI-003")
            if r.reason == "forbidden-char":
                sev = Severity.MEDIUM
            findings.append(Finding(
                rule_id=rule_id,
                severity=sev,
                message=r.detail,
                subject=cand,
                line=lineno,
                path=ctx["path"],
                hint="See the DOI Handbook section 2.5.1.",
                citation="DOI Handbook (handbook.doi.org) 2.5.1",
            ))
    return findings


def _check_arxiv_lines(ctx: dict, options: Options) -> List[Finding]:
    findings: List[Finding] = []
    for lineno, line in ctx["lines"]:
        for m in _ARXIV_LINE_RE.finditer(line):
            cand = m.group(1)
            r = validate_arxiv_id(cand, current_year=options.current_year)
            if r.ok:
                continue
            if r.reason == "future-year":
                rule_id = "DOI-005"
                sev = Severity.MEDIUM
            else:
                rule_id = "DOI-004"
                sev = Severity.HIGH
            findings.append(Finding(
                rule_id=rule_id,
                severity=sev,
                message=r.detail,
                subject=cand,
                line=lineno,
                path=ctx["path"],
                hint="See info.arxiv.org/help/arxiv_identifier.html.",
                citation="arXiv identifier scheme (info.arxiv.org)",
            ))
    return findings


def _check_orcid_lines(ctx: dict, options: Options) -> List[Finding]:
    findings: List[Finding] = []
    for lineno, line in ctx["lines"]:
        for m in _ORCID_LINE_RE.finditer(line):
            cand = m.group(1)
            r = validate_orcid(cand)
            if r.ok:
                continue
            rule_id = "DOI-007" if r.reason == "bad-shape" else "DOI-006"
            findings.append(Finding(
                rule_id=rule_id,
                severity=Severity.HIGH,
                message=r.detail,
                subject=cand,
                line=lineno,
                path=ctx["path"],
                hint="ORCID uses ISO 7064 Mod 11,2 for the final character.",
                citation="support.orcid.org (ISO 7064 Mod 11,2)",
            ))
    return findings


def _check_isbn_lines(ctx: dict, options: Options) -> List[Finding]:
    findings: List[Finding] = []
    for lineno, line in ctx["lines"]:
        for m in _ISBN_LINE_RE.finditer(line):
            cand = m.group(1).strip()
            r = validate_isbn(cand)
            if r.ok:
                continue
            if r.reason in ("bad-length",):
                continue  # Not an ISBN; fall through quietly.
            if "isbn10" in r.reason:
                rule_id = "DOI-008"
            elif "isbn13" in r.reason:
                rule_id = "DOI-009"
            else:
                rule_id = "DOI-008"
            findings.append(Finding(
                rule_id=rule_id,
                severity=Severity.HIGH,
                message=r.detail,
                subject=cand,
                line=lineno,
                path=ctx["path"],
                hint="ISBN-10 uses mod-11; ISBN-13 uses mod-10 with"
                     " alternating weights 1 and 3.",
                citation="ISO 2108 (ISBN) summary at isbn-international.org",
            ))
    return findings


# ---------------------------------------------------------------------------
# BibTeX hygiene rules.
# ---------------------------------------------------------------------------

def _check_required_fields(ctx: dict, options: Options) -> List[Finding]:
    findings: List[Finding] = []
    for e in ctx["entries"]:
        req = REQUIRED_FIELDS.get(e.entry_type)
        if req is None:
            continue
        for group in req:
            if not any(f in e.fields for f in group):
                findings.append(Finding(
                    rule_id="DOI-010",
                    severity=Severity.MEDIUM,
                    message=(
                        "@" + e.entry_type + "{" + e.key
                        + "} missing required field: "
                        + " or ".join(group)
                    ),
                    subject=e.key,
                    line=e.line,
                    path=ctx["path"],
                    hint="Add the missing field or switch to @misc if the"
                         " citation genuinely lacks it.",
                    citation="BibTeX user's guide, Entry types",
                ))
    return findings


def _check_future_year(ctx: dict, options: Options) -> List[Finding]:
    findings: List[Finding] = []
    for e in ctx["entries"]:
        y = e.fields.get("year", "").strip()
        if not y:
            continue
        try:
            yr = int(y)
        except ValueError:
            # Not numeric; let other rules handle shape.
            continue
        if yr > options.current_year:
            findings.append(Finding(
                rule_id="DOI-011",
                severity=Severity.MEDIUM,
                message=(
                    "@" + e.entry_type + "{" + e.key + "} year " + y
                    + " is in the future (current year "
                    + str(options.current_year) + ")"
                ),
                subject=e.key,
                line=e.field_lines.get("year", e.line),
                path=ctx["path"],
                hint="A future year typically indicates a hallucinated or"
                     " uncorrected citation.",
                citation="Internal consistency; see 2026 citation-hallucination"
                         " studies (CheckIfExist arXiv 2602.15871)",
            ))
    return findings


def _check_empty_values(ctx: dict, options: Options) -> List[Finding]:
    findings: List[Finding] = []
    for e in ctx["entries"]:
        for name, val in e.fields.items():
            if val is None or val.strip() == "":
                findings.append(Finding(
                    rule_id="DOI-012",
                    severity=Severity.MEDIUM,
                    message=(
                        "@" + e.entry_type + "{" + e.key + "} field '"
                        + name + "' has an empty value"
                    ),
                    subject=e.key + "." + name,
                    line=e.field_lines.get(name, e.line),
                    path=ctx["path"],
                    hint="Delete the field or supply a value; an empty"
                         " field hides a missing citation.",
                    citation="BibTeX user's guide",
                ))
    return findings


def _check_duplicate_keys(ctx: dict, options: Options) -> List[Finding]:
    findings: List[Finding] = []
    seen: Dict[str, int] = {}
    for e in ctx["entries"]:
        if not e.key:
            continue
        if e.key in seen:
            findings.append(Finding(
                rule_id="DOI-013",
                severity=Severity.HIGH,
                message=(
                    "duplicate BibTeX cite key '" + e.key
                    + "' - previous at line " + str(seen[e.key])
                ),
                subject=e.key,
                line=e.line,
                path=ctx["path"],
                hint="Only the last entry with a duplicate key is used by"
                     " LaTeX; renames the duplicates.",
                citation="BibTeX user's guide",
            ))
        else:
            seen[e.key] = e.line
    return findings


def _check_unbalanced_braces(ctx: dict, options: Options) -> List[Finding]:
    findings: List[Finding] = []
    for e in ctx["entries"]:
        for name in e.unbalanced_fields:
            if name == "<entry>":
                msg = (
                    "@" + e.entry_type + "{" + e.key + "} outer braces"
                    " are unterminated"
                )
                subj = e.key
            else:
                msg = (
                    "@" + e.entry_type + "{" + e.key + "} field '" + name
                    + "' has unbalanced braces"
                )
                subj = e.key + "." + name
            findings.append(Finding(
                rule_id="DOI-014",
                severity=Severity.MEDIUM,
                message=msg,
                subject=subj,
                line=e.field_lines.get(name, e.line),
                path=ctx["path"],
                hint="BibTeX silently truncates values whose braces do"
                     " not balance.",
                citation="BibTeX user's guide, field values",
            ))
    return findings


def _check_bibtex_identifiers(ctx: dict, options: Options) -> List[Finding]:
    """DOI-015: validate DOI / arXiv / ISBN values that appear INSIDE
    BibTeX entry fields (doi=, eprint=, isbn=, archiveprefix=/eprint=).
    """
    findings: List[Finding] = []
    for e in ctx["entries"]:
        doi = e.fields.get("doi", "").strip()
        if doi:
            r = validate_doi(doi)
            if not r.ok:
                findings.append(Finding(
                    rule_id="DOI-015",
                    severity=Severity.HIGH,
                    message=(
                        "@" + e.entry_type + "{" + e.key + "} doi field: "
                        + r.detail
                    ),
                    subject=e.key + ".doi",
                    line=e.field_lines.get("doi", e.line),
                    path=ctx["path"],
                    hint="See DOI Handbook 2.5.1.",
                    citation="DOI Handbook 2.5.1",
                ))
        eprint = e.fields.get("eprint", "").strip()
        archp = e.fields.get("archiveprefix", "").strip().lower()
        if eprint and (archp == "arxiv" or not archp):
            r = validate_arxiv_id(
                eprint, current_year=options.current_year,
            )
            if not r.ok:
                findings.append(Finding(
                    rule_id="DOI-015",
                    severity=Severity.HIGH,
                    message=(
                        "@" + e.entry_type + "{" + e.key
                        + "} eprint field (arXiv): " + r.detail
                    ),
                    subject=e.key + ".eprint",
                    line=e.field_lines.get("eprint", e.line),
                    path=ctx["path"],
                    hint="arXiv identifiers are YYMM.NNNN(N) since 2007-04.",
                    citation="arXiv identifier scheme",
                ))
        isbn = e.fields.get("isbn", "").strip()
        if isbn:
            r = validate_isbn(isbn)
            if not r.ok and r.reason != "bad-length":
                findings.append(Finding(
                    rule_id="DOI-015",
                    severity=Severity.HIGH,
                    message=(
                        "@" + e.entry_type + "{" + e.key + "} isbn field: "
                        + r.detail
                    ),
                    subject=e.key + ".isbn",
                    line=e.field_lines.get("isbn", e.line),
                    path=ctx["path"],
                    hint="ISBN-10 mod-11 or ISBN-13 mod-10 per ISO 2108.",
                    citation="ISO 2108",
                ))
    return findings


# ---------------------------------------------------------------------------
# Registry.
# ---------------------------------------------------------------------------

REGISTRY: List[Rule] = [
    Rule("DOI-001", Severity.HIGH,
         "Malformed DOI prefix",
         "DOI prefix must match '10.<digits>[.<digits>...]'.",
         "DOI Handbook 2.5.1",
         _check_doi_lines),
    Rule("DOI-002", Severity.HIGH,
         "DOI missing slash or empty suffix",
         "A DOI must contain '/' with a non-empty suffix.",
         "DOI Handbook 2.5.1",
         _check_doi_lines),
    Rule("DOI-003", Severity.MEDIUM,
         "DOI contains whitespace or control characters",
         "DOI strings may not contain whitespace or ASCII control chars.",
         "DOI Handbook 2.5.1",
         _check_doi_lines),
    Rule("DOI-004", Severity.HIGH,
         "Malformed arXiv ID",
         "arXiv ID must match new-style YYMM.NNNN(N) or old-style"
         " archive/subj-class/YYMMNNN.",
         "arXiv identifier scheme (info.arxiv.org)",
         _check_arxiv_lines),
    Rule("DOI-005", Severity.MEDIUM,
         "arXiv ID has implausible or future date",
         "YYMM in an arXiv ID must be a plausible past month and valid"
         " for new-style (>= 2007-04).",
         "arXiv identifier scheme",
         _check_arxiv_lines),
    Rule("DOI-006", Severity.HIGH,
         "ORCID checksum failure",
         "ORCID iD final character must match ISO 7064 Mod 11,2.",
         "ORCID support (ISO 7064 Mod 11,2)",
         _check_orcid_lines),
    Rule("DOI-007", Severity.HIGH,
         "Malformed ORCID shape",
         "ORCID iD must be 16 characters grouped 4-4-4-4.",
         "ORCID support",
         _check_orcid_lines),
    Rule("DOI-008", Severity.HIGH,
         "ISBN-10 checksum failure",
         "ISBN-10 must satisfy mod-11 per ISO 2108.",
         "ISO 2108",
         _check_isbn_lines),
    Rule("DOI-009", Severity.HIGH,
         "ISBN-13 checksum failure",
         "ISBN-13 must satisfy mod-10 with alternating weights per ISO 2108.",
         "ISO 2108",
         _check_isbn_lines),
    Rule("DOI-010", Severity.MEDIUM,
         "BibTeX entry missing a required field",
         "BibTeX entries carry a required-field list per type.",
         "BibTeX user's guide",
         _check_required_fields),
    Rule("DOI-011", Severity.MEDIUM,
         "BibTeX entry year is in the future",
         "A BibTeX year > current year indicates a hallucinated or"
         " uncorrected citation.",
         "2026 citation-hallucination studies",
         _check_future_year),
    Rule("DOI-012", Severity.MEDIUM,
         "BibTeX field has an empty value",
         "Empty-valued fields silently hide missing citations.",
         "BibTeX user's guide",
         _check_empty_values),
    Rule("DOI-013", Severity.HIGH,
         "Duplicate BibTeX cite key",
         "LaTeX silently uses only the last entry with a duplicate key.",
         "BibTeX user's guide",
         _check_duplicate_keys),
    Rule("DOI-014", Severity.MEDIUM,
         "BibTeX field has unbalanced braces",
         "BibTeX silently truncates values with unbalanced braces.",
         "BibTeX user's guide",
         _check_unbalanced_braces),
    Rule("DOI-015", Severity.HIGH,
         "BibTeX doi/eprint/isbn field is not a well-formed identifier",
         "Validate DOI, arXiv ID, and ISBN values embedded in BibTeX"
         " entries against the identifier rules above.",
         "DOI Handbook, arXiv scheme, ISO 2108",
         _check_bibtex_identifiers),
]


def _run_check_once(
    check: Check, ctx: dict, options: Options
) -> List[Finding]:
    out: List[Finding] = []
    for f in check(ctx, options):
        if not options.rule_enabled(f.rule_id):
            continue
        if f.severity is Severity.INFO and not (
            options.include_info or options.strict
        ):
            continue
        out.append(f)
    return out


def run_all(
    text: str, path: str, options: Options
) -> List[Finding]:
    """Run every enabled rule over the file content ``text``.

    The context dict carries both the raw lines (for line-based identifier
    rules) and the parsed BibTeX entries (for BibTeX rules). Each rule is
    pure.
    """
    # Lazy-build the lines once per file.
    lines = [(i + 1, line) for i, line in enumerate(text.splitlines())]
    entries = parse_bibtex(text) if "@" in text else []
    ctx = {
        "path": path,
        "text": text,
        "lines": lines,
        "entries": entries,
    }
    # Deduplicate by rule function identity - several rule IDs share the
    # same check callable (e.g. DOI-001..003 all come from _check_doi_lines)
    # and we want each line-based check to run exactly once.
    seen_checks: set = set()
    findings: List[Finding] = []
    for rule in REGISTRY:
        if rule.check in seen_checks:
            continue
        seen_checks.add(rule.check)
        findings.extend(_run_check_once(rule.check, ctx, options))
    return findings


__all__ = [
    "Check",
    "Rule",
    "REGISTRY",
    "run_all",
]
