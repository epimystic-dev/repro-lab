"""Notebook parsing and export.

A Jupyter .ipynb file is JSON. The schema is public (nbformat v4) and
every field this module reads is documented. Parsing is deliberately
tolerant: a non-conforming field becomes a finding, not a crash.

Public spec sources paraphrased (never vendored):

  - nbformat v4 notebook schema (jupyter.org/nbformat docs): the
    top-level keys ``cells``, ``metadata``, ``nbformat`` and
    ``nbformat_minor``; the cell keys ``cell_type``, ``source``,
    ``execution_count`` and ``outputs``.
  - nbformat metadata keys ``kernelspec`` and ``language_info``.

A clean run means the notebook's execution record is internally
consistent against the named checklist. It never guarantees that a
top-to-bottom execution would succeed or produce the recorded outputs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CodeCell:
    index: int                       # 0-based position in file order
    source: str                      # joined source lines
    execution_count: Optional[int]   # None if never-run or cleared
    metadata: Dict[str, Any] = field(default_factory=dict)
    outputs: List[Any] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.source.strip()


@dataclass
class Notebook:
    code_cells: List[CodeCell] = field(default_factory=list)
    kernel_name: Optional[str] = None
    language_name: Optional[str] = None
    nbformat: Optional[int] = None
    nbformat_minor: Optional[int] = None
    parse_error: Optional[str] = None


def _join_source(src: Any) -> str:
    if isinstance(src, list):
        return "".join(x for x in src if isinstance(x, str))
    if isinstance(src, str):
        return src
    return ""


def parse_notebook(content: str) -> Notebook:
    nb = Notebook()
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as e:
        nb.parse_error = "invalid JSON: " + str(e)
        return nb
    if not isinstance(obj, dict):
        nb.parse_error = "top-level is not a JSON object"
        return nb
    nb.nbformat = obj.get("nbformat") if isinstance(
        obj.get("nbformat"), int) else None
    nb.nbformat_minor = obj.get("nbformat_minor") if isinstance(
        obj.get("nbformat_minor"), int) else None
    meta = obj.get("metadata") or {}
    if isinstance(meta, dict):
        ks = meta.get("kernelspec") or {}
        if isinstance(ks, dict):
            nb.kernel_name = ks.get("name") if isinstance(
                ks.get("name"), str) else None
        li = meta.get("language_info") or {}
        if isinstance(li, dict):
            nb.language_name = li.get("name") if isinstance(
                li.get("name"), str) else None
    cells = obj.get("cells") or []
    if not isinstance(cells, list):
        nb.parse_error = "cells is not a list"
        return nb
    for i, c in enumerate(cells):
        if not isinstance(c, dict):
            continue
        if c.get("cell_type") != "code":
            continue
        ec = c.get("execution_count")
        if not (ec is None or isinstance(ec, int)):
            ec = None
        nb.code_cells.append(CodeCell(
            index=i,
            source=_join_source(c.get("source")),
            execution_count=ec,
            metadata=c.get("metadata") or {},
            outputs=c.get("outputs") or [],
            raw=c,
        ))
    return nb


# A conservative set of simple-identifier assignment / import patterns.
# A full AST walk would be ideal; the project is standard-library-only
# and ``ast`` on a merged script works, but on a per-cell basis we need
# to be tolerant of partial source (not every cell parses cleanly). We
# use regex at the per-cell level and only promote to a finding when the
# evidence is unambiguous.
_IMPORT_LINE = re.compile(
    r"^\s*(?:from\s+([A-Za-z_][A-Za-z0-9_\.]*)\s+import\s+(.+)|"
    r"import\s+([A-Za-z_][A-Za-z0-9_\.]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_\.]*)*))",
    re.MULTILINE,
)

_SIMPLE_NAME = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


def _declared_names(src: str) -> List[str]:
    """Names a cell plausibly introduces into the global scope.

    Covers imports (``import x`` and ``from x import a, b``) and
    simple top-level assignments ``name = ...``. Returns a flat list
    of names (duplicates allowed; callers de-dup).
    """
    out: List[str] = []
    for m in _IMPORT_LINE.finditer(src):
        if m.group(1):
            targets = m.group(2)
            for part in targets.split(","):
                part = part.strip()
                if " as " in part:
                    part = part.split(" as ", 1)[1].strip()
                if part and part != "*":
                    out.append(part)
        elif m.group(3):
            for mod in m.group(3).split(","):
                mod = mod.strip()
                if " as " in mod:
                    mod = mod.split(" as ", 1)[1].strip()
                if mod:
                    out.append(mod.split(".", 1)[0])
    # Simple top-level assignments: `name = value` with no leading
    # whitespace. Walrus and augmented assignments are ignored to keep
    # the heuristic conservative.
    for line in src.splitlines():
        if not line or line[0] in " \t#":
            continue
        if "=" not in line or line.strip().startswith("#"):
            continue
        head = line.split("=", 1)[0].strip()
        # Skip comparisons (==, !=), augmented (+=, -=, ...), typed decls
        # (``name: int = 1`` is fine, name is still introduced).
        if head.endswith("!") or head.endswith("=") or head.endswith("<") or \
                head.endswith(">"):
            continue
        if ":" in head:
            head = head.split(":", 1)[0].strip()
        if _SIMPLE_NAME.fullmatch(head):
            out.append(head)
    return out


def _referenced_names(src: str) -> List[str]:
    """Identifiers referenced anywhere in the source (approximate)."""
    out: List[str] = []
    in_string = False
    quote = ""
    i = 0
    buf = []
    while i < len(src):
        ch = src[i]
        if in_string:
            if ch == "\\" and i + 1 < len(src):
                i += 2
                continue
            if ch == quote:
                in_string = False
            i += 1
            continue
        if ch in '"\'':
            # Triple-quoted strings are collapsed via the same loop as
            # a slight over-approximation; good enough for name counting.
            in_string = True
            quote = ch
            i += 1
            continue
        if ch == "#":
            # Skip to end of line.
            while i < len(src) and src[i] != "\n":
                i += 1
            continue
        buf.append(ch)
        i += 1
    stripped = "".join(buf)
    for m in _SIMPLE_NAME.finditer(stripped):
        out.append(m.group(1))
    return out


# A small denylist of names that are either stdlib builtins or so
# commonly imported that referencing them does not count as an
# "undefined" use for NBX-005.
_BUILTINS = frozenset({
    "print", "len", "range", "list", "dict", "set", "tuple", "str", "int",
    "float", "bool", "None", "True", "False", "if", "else", "elif", "for",
    "while", "def", "class", "return", "import", "from", "as", "in", "is",
    "not", "and", "or", "pass", "break", "continue", "try", "except",
    "finally", "raise", "with", "lambda", "yield", "global", "nonlocal",
    "assert", "del", "self", "cls", "type", "input", "open", "min", "max",
    "sum", "map", "filter", "zip", "enumerate", "sorted", "reversed",
    "abs", "all", "any", "round", "isinstance", "issubclass", "hasattr",
    "getattr", "setattr", "delattr", "callable", "iter", "next", "object",
    "repr", "id", "hash", "format", "ord", "chr", "bytes", "bytearray",
    "memoryview", "property", "staticmethod", "classmethod", "super",
})


__all__ = [
    "CodeCell",
    "Notebook",
    "parse_notebook",
    "_declared_names",
    "_referenced_names",
    "_BUILTINS",
]
