"""Minimal, standards-paraphrased BibTeX parser and hygiene helpers.

The parser is intentionally forgiving - it treats a BibTeX file as a
stream of @type{key, field = value, ...} entries and does not validate
LaTeX macros. The purpose is to find structural defects (missing required
fields, duplicate keys, unbalanced braces inside field values, empty
values, future year) that already fire inside the author's own file,
regardless of whether the entries later resolve.

Reference (public): the BibTeX user's guide (bibtex-style.pdf, Oren
Patashnik 1988, public domain) names the "required" and "optional" fields
per entry type. The required-field table below paraphrases that document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# Required-field table per BibTeX entry type. Alternatives are a tuple;
# "any one of" satisfies the requirement.
#
# Paraphrased from BibTeX user guide section "Entry types" (public).
REQUIRED_FIELDS: Dict[str, Tuple[Tuple[str, ...], ...]] = {
    "article":        (("author",), ("title",), ("journal",), ("year",)),
    "book":           (("author", "editor"), ("title",),
                       ("publisher",), ("year",)),
    "booklet":        (("title",),),
    "inbook":         (("author", "editor"), ("title",),
                       ("chapter", "pages"), ("publisher",), ("year",)),
    "incollection":   (("author",), ("title",), ("booktitle",),
                       ("publisher",), ("year",)),
    "inproceedings":  (("author",), ("title",), ("booktitle",), ("year",)),
    "conference":     (("author",), ("title",), ("booktitle",), ("year",)),
    "manual":         (("title",),),
    "mastersthesis":  (("author",), ("title",), ("school",), ("year",)),
    "misc":           (),
    "phdthesis":      (("author",), ("title",), ("school",), ("year",)),
    "proceedings":    (("title",), ("year",)),
    "techreport":     (("author",), ("title",), ("institution",), ("year",)),
    "unpublished":    (("author",), ("title",), ("note",)),
}


@dataclass
class BibEntry:
    """One @type{key, ...} entry."""

    entry_type: str
    key: str
    fields: Dict[str, str] = field(default_factory=dict)
    line: int = 0
    field_lines: Dict[str, int] = field(default_factory=dict)
    unbalanced_fields: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser - a small state machine. Not a general LaTeX parser.
# ---------------------------------------------------------------------------

_ENTRY_HEAD_RE = re.compile(r"@([A-Za-z]+)\s*[\{\(]\s*", re.MULTILINE)


def _skip_to_entry(text: str, pos: int) -> Optional[int]:
    """Advance to the next '@type{' header or return None at EOF."""
    while pos < len(text):
        ch = text[pos]
        if ch == "%":
            # Line comment - skip to end of line.
            nl = text.find("\n", pos)
            pos = len(text) if nl < 0 else nl + 1
            continue
        if ch == "@":
            return pos
        pos += 1
    return None


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _read_balanced(text: str, pos: int, open_ch: str, close_ch: str
                   ) -> Tuple[Optional[str], int, bool]:
    """Read a balanced {...} or (...) span starting at ``pos`` which points
    AT the opening character. Returns (span_without_outer, pos_after,
    balanced_ok).

    If the span is unterminated we still return what we have and
    ``balanced_ok=False``.
    """
    if text[pos] != open_ch:
        return None, pos, False
    depth = 1
    start = pos + 1
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            # Skip the escaped char.
            i += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1, True
        i += 1
    return text[start:], n, False


def _braces_balanced(value: str) -> bool:
    """Does the field value have balanced braces when backslashes do not
    protect brace characters? BibTeX itself requires balance after a
    one-level nesting of \\{ \\} escapes, so we conservatively ignore
    anything preceded by a backslash.
    """
    depth = 0
    i = 0
    n = len(value)
    while i < n:
        c = value[i]
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


def _parse_fields(body: str, body_start_line: int
                  ) -> Tuple[str, Dict[str, str], Dict[str, int], List[str]]:
    """Parse the inside of an entry. The first token up to the first comma
    is the citation key. Returns (key, fields, field_line_map,
    unbalanced_field_names).
    """
    key, _, rest = body.partition(",")
    key = key.strip()
    fields: Dict[str, str] = {}
    field_lines: Dict[str, int] = {}
    unbalanced: List[str] = []
    i = 0
    text = rest
    n = len(text)
    while i < n:
        # Skip whitespace and comments.
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        # Read field name.
        name_start = i
        while i < n and (text[i].isalnum() or text[i] in "-_"):
            i += 1
        name = text[name_start:i].strip().lower()
        if not name:
            break
        # Skip to "=".
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n or text[i] != "=":
            break
        i += 1
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        # Read value: {...}, "..." or a bare word up to ",".
        line_here = body_start_line + text.count("\n", 0, name_start)
        if text[i] == "{":
            val, i, ok = _read_balanced(text, i, "{", "}")
            if val is None:
                break
            if not ok or not _braces_balanced(val):
                unbalanced.append(name)
            fields[name] = val
            field_lines[name] = line_here
        elif text[i] == '"':
            start = i + 1
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
            val = text[start:i]
            if i < n:
                i += 1
            fields[name] = val
            field_lines[name] = line_here
            if not _braces_balanced(val):
                unbalanced.append(name)
        else:
            start = i
            while i < n and text[i] not in ",\n":
                i += 1
            fields[name] = text[start:i].strip()
            field_lines[name] = line_here
        # Skip comma and whitespace.
        while i < n and text[i] in " \t\r\n,":
            i += 1
    return key, fields, field_lines, unbalanced


def parse_bibtex(text: str) -> List[BibEntry]:
    """Walk ``text`` and return the entries it contains, in document order.

    Unparseable regions are skipped silently - the aim is lint, not strict
    syntax validation.
    """
    entries: List[BibEntry] = []
    pos = 0
    n = len(text)
    while pos < n:
        p = _skip_to_entry(text, pos)
        if p is None:
            break
        m = _ENTRY_HEAD_RE.match(text, p)
        if not m:
            pos = p + 1
            continue
        etype = m.group(1).lower()
        head_end = m.end()
        # Determine the opening bracket we matched: either "{" or "(".
        # We look at the character immediately before head_end.
        # The regex eats trailing whitespace, so step back to find it.
        bracket_pos = head_end - 1
        while bracket_pos > p and text[bracket_pos] in " \t\r\n":
            bracket_pos -= 1
        open_ch = text[bracket_pos]
        close_ch = "}" if open_ch == "{" else ")"
        body, after, body_ok = _read_balanced(
            text, bracket_pos, open_ch, close_ch,
        )
        if body is None:
            pos = p + 1
            continue
        line = _line_of(text, p)
        body_line = _line_of(text, bracket_pos + 1)
        key, fields, field_lines, unbalanced = _parse_fields(
            body, body_line,
        )
        # If the entry body itself was unterminated at EOF, that is a
        # BibTeX hygiene defect (silently truncated field values and
        # swallowed later entries). Mark it with a sentinel field name.
        if not body_ok:
            unbalanced.append("<entry>")
        entries.append(BibEntry(
            entry_type=etype,
            key=key,
            fields=fields,
            line=line,
            field_lines=field_lines,
            unbalanced_fields=unbalanced,
        ))
        pos = after
    return entries


__all__ = [
    "BibEntry",
    "REQUIRED_FIELDS",
    "parse_bibtex",
]
