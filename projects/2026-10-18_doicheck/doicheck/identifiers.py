"""Format and checksum validators for scholarly identifiers.

Every validator here is **offline**: it checks the shape of the string
against the public spec, computes the checksum where one is defined, and
returns a reason-coded failure if any check fails. No validator opens a
socket. A clean validator result means the identifier is **well-formed**,
never that it resolves to a real record.

Sources (public, paraphrased):

  * DOI Handbook (handbook.doi.org) - a DOI is a prefix "10." + registrant
    code (numeric, dot-separated allowed) + "/" + an opaque suffix. The
    suffix is case-insensitive and may contain any printable character
    except whitespace per section 2.5.1.
  * arXiv identifier scheme (info.arxiv.org/help/arxiv_identifier.html) -
    old-style archive.subj-class/YYMMNNN (NNN = 3-digit), new-style since
    2007-04 is YYMM.NNNN or YYMM.NNNNN with optional "vN" version suffix.
  * ORCID (support.orcid.org) - 16 digits grouped 4-4-4-4 by hyphens,
    final character is checksum computed with ISO 7064 Mod 11,2 ("X"
    represents 10).
  * ISBN-10 (ISO 2108) - 10 digits, final a checksum (digit or "X")
    computed as sum_{i=1..9} i*d_i mod 11.
  * ISBN-13 (ISO 2108) - 13 digits, final a checksum computed as
    10 - (sum_{i=0..5}(d_{2i}) + 3*sum_{i=0..5}(d_{2i+1})) mod 10, with
    the result 10 mapping back to 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating one identifier string.

    ``ok`` is True when the identifier is well-formed. ``reason`` is a
    short, stable, machine-readable code when it is not; ``detail`` is a
    human-readable sentence suitable for a report.
    """

    ok: bool
    reason: str = ""
    detail: str = ""


# ---------------------------------------------------------------------------
# DOI
# ---------------------------------------------------------------------------

# A DOI prefix is literally "10." followed by one or more digits, optionally
# with dotted sub-registrant codes (e.g. 10.1000, 10.1038, 10.1145.1234).
# The suffix starts after the first slash and runs to the end of the DOI
# string; per the DOI Handbook section 2.5.1 it may contain any printable
# character except whitespace.
_DOI_PREFIX_RE = re.compile(r"^10\.\d+(?:\.[A-Za-z0-9]+)*$")
# Characters that must NOT appear in a DOI (whitespace or ASCII control).
_DOI_FORBIDDEN_RE = re.compile(r"[\x00-\x20]")


def validate_doi(s: str) -> ValidationResult:
    """Check that ``s`` is a well-formed DOI.

    Does NOT verify that the DOI resolves - this is an offline tool.
    """
    if not isinstance(s, str) or not s:
        return ValidationResult(False, "empty", "empty DOI string")
    if "/" not in s:
        return ValidationResult(
            False, "no-slash",
            "DOI must contain a '/' separating prefix and suffix",
        )
    prefix, _, suffix = s.partition("/")
    if not _DOI_PREFIX_RE.match(prefix):
        return ValidationResult(
            False, "bad-prefix",
            "DOI prefix must match 10.<digits>[.<digits>...]",
        )
    if not suffix or not suffix.strip():
        return ValidationResult(
            False, "empty-suffix",
            "DOI suffix is empty or whitespace-only",
        )
    if _DOI_FORBIDDEN_RE.search(s):
        return ValidationResult(
            False, "forbidden-char",
            "DOI contains whitespace or ASCII control characters",
        )
    return ValidationResult(True)


# ---------------------------------------------------------------------------
# arXiv ID
# ---------------------------------------------------------------------------

# New-style arXiv: YYMM.NNNN or YYMM.NNNNN, optional vN version suffix.
# info.arxiv.org/help/arxiv_identifier.html specifies 4-digit NNNN before
# 2015-01 and 5-digit NNNNN from 2015-01 onward; we accept both.
_ARXIV_NEW_RE = re.compile(r"^(\d{2})(\d{2})\.(\d{4,5})(v\d+)?$")

# Old-style arXiv: archive/subj-class/YYMMNNN (3-digit NNN). Archives can
# contain letters, dots, and hyphens (e.g. "math.AG", "cond-mat.stat-mech").
_ARXIV_OLD_RE = re.compile(
    r"^([a-z][a-z\-]+(?:\.[A-Z]{2})?)/(\d{2})(\d{2})(\d{3})(v\d+)?$"
)


def validate_arxiv_id(
    s: str, current_year: int = 2026
) -> ValidationResult:
    """Check that ``s`` is a well-formed arXiv identifier.

    Does NOT check that the paper exists.
    """
    if not isinstance(s, str) or not s:
        return ValidationResult(False, "empty", "empty arXiv ID")
    s = s.strip()
    # Strip a leading "arXiv:" if present - common in BibTeX fields.
    if s.lower().startswith("arxiv:"):
        s = s[6:]
    m = _ARXIV_NEW_RE.match(s)
    if m:
        yy, mm, _nnnnn, _ver = m.groups()
        month = int(mm)
        if month < 1 or month > 12:
            return ValidationResult(
                False, "bad-month",
                "arXiv ID month " + mm + " is not 01-12",
            )
        year = 2000 + int(yy)
        if year > current_year:
            return ValidationResult(
                False, "future-year",
                "arXiv ID year " + str(year)
                + " is in the future (current year "
                + str(current_year) + ")",
            )
        if year < 2007 or (year == 2007 and month < 4):
            return ValidationResult(
                False, "pre-2007-new-style",
                "new-style arXiv IDs begin 2007-04; " + s
                + " claims an earlier date",
            )
        return ValidationResult(True)
    m = _ARXIV_OLD_RE.match(s)
    if m:
        _archive, yy, mm, _nnn, _ver = m.groups()
        month = int(mm)
        if month < 1 or month > 12:
            return ValidationResult(
                False, "bad-month",
                "arXiv old-style month " + mm + " is not 01-12",
            )
        return ValidationResult(True)
    return ValidationResult(
        False, "bad-format",
        "arXiv ID matches neither new-style (YYMM.NNNN(N)) nor old-style"
        " (archive/subj-class/YYMMNNN)",
    )


# ---------------------------------------------------------------------------
# ORCID - 16 digits, 4-4-4-4 hyphenated, ISO 7064 Mod 11,2 checksum.
# ---------------------------------------------------------------------------

_ORCID_SHAPE_RE = re.compile(r"^(\d{4})-(\d{4})-(\d{4})-(\d{3}[\dX])$")


def _orcid_checksum_ok(digits_15: str, last: str) -> bool:
    """ISO 7064 Mod 11,2 - public algorithm.

    total = 0; for each digit left-to-right: total = (total + d) * 2.
    result = (12 - (total mod 11)) mod 11. "10" is written "X".
    """
    total = 0
    for ch in digits_15:
        total = (total + int(ch)) * 2
    remainder = total % 11
    check = (12 - remainder) % 11
    expected = "X" if check == 10 else str(check)
    return expected == last


def validate_orcid(s: str) -> ValidationResult:
    """Check that ``s`` is a well-formed ORCID iD."""
    if not isinstance(s, str) or not s:
        return ValidationResult(False, "empty", "empty ORCID string")
    s = s.strip()
    # Strip a URL prefix if present.
    for prefix in ("https://orcid.org/", "http://orcid.org/", "orcid.org/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    m = _ORCID_SHAPE_RE.match(s)
    if not m:
        return ValidationResult(
            False, "bad-shape",
            "ORCID must be 16 characters grouped 4-4-4-4 with digits"
            " and a final digit or 'X'",
        )
    g1, g2, g3, g4 = m.groups()
    digits_15 = g1 + g2 + g3 + g4[:3]
    last = g4[3]
    if not _orcid_checksum_ok(digits_15, last):
        return ValidationResult(
            False, "bad-checksum",
            "ORCID checksum (ISO 7064 Mod 11,2) does not match the digits",
        )
    return ValidationResult(True)


# ---------------------------------------------------------------------------
# ISBN-10 / ISBN-13 - mod-10 and mod-13 per ISO 2108.
# ---------------------------------------------------------------------------


def _clean_isbn(s: str) -> str:
    """Strip ISBN prefix, hyphens, and spaces. Keep X as uppercase."""
    s = s.strip()
    for prefix in ("ISBN:", "ISBN", "isbn:", "isbn"):
        if s.startswith(prefix):
            s = s[len(prefix):].lstrip(" \t-")
            break
    return s.replace("-", "").replace(" ", "").upper()


def _isbn10_checksum_ok(d: str) -> bool:
    total = 0
    for i, ch in enumerate(d, start=1):
        if i == 10 and ch == "X":
            total += 10 * 10
            continue
        if not ch.isdigit():
            return False
        total += i * int(ch)
    return total % 11 == 0


def _isbn13_checksum_ok(d: str) -> bool:
    if not d.isdigit():
        return False
    total = 0
    for i, ch in enumerate(d):
        n = int(ch)
        total += n if i % 2 == 0 else 3 * n
    return total % 10 == 0


def validate_isbn(s: str) -> ValidationResult:
    """Check that ``s`` is a well-formed ISBN-10 or ISBN-13."""
    if not isinstance(s, str) or not s:
        return ValidationResult(False, "empty", "empty ISBN string")
    cleaned = _clean_isbn(s)
    if len(cleaned) == 10:
        if not _isbn10_checksum_ok(cleaned):
            return ValidationResult(
                False, "bad-isbn10-checksum",
                "ISBN-10 mod-10 checksum does not match",
            )
        return ValidationResult(True)
    if len(cleaned) == 13:
        if not _isbn13_checksum_ok(cleaned):
            return ValidationResult(
                False, "bad-isbn13-checksum",
                "ISBN-13 mod-10 checksum does not match",
            )
        return ValidationResult(True)
    return ValidationResult(
        False, "bad-length",
        "ISBN must be 10 or 13 digits after stripping punctuation; got "
        + str(len(cleaned)),
    )


__all__ = [
    "ValidationResult",
    "validate_doi",
    "validate_arxiv_id",
    "validate_orcid",
    "validate_isbn",
]
