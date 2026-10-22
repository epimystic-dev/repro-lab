"""Shared test helpers for seedaudit."""

from __future__ import annotations

import io
import os
import tempfile
from typing import Iterable, Optional, Sequence, Tuple

from seedaudit.analyzer import analyze
from seedaudit.cli import main as cli_main
from seedaudit.rules import run_all
from seedaudit.types import Finding, Options


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
_LOCAL_TMP = os.path.join(_PROJECT_ROOT, ".pytest_tmp")
os.makedirs(_LOCAL_TMP, exist_ok=True)
tempfile.tempdir = _LOCAL_TMP


def scan_string(
    source: str,
    options: Optional[Options] = None,
    path: str = "in-memory.py",
) -> Sequence[Finding]:
    options = options or Options()
    result = analyze(source, path)
    return run_all(result, path, options)


def write_temp(
    content: str, name: str = "sample.py",
) -> Tuple[str, str]:
    d = tempfile.mkdtemp(prefix="seedaudit_")
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return d, p


def run_cli(argv: Sequence[str]) -> Tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    rc = cli_main(list(argv), stdout=out, stderr=err)
    return rc, out.getvalue(), err.getvalue()


def rule_ids(findings: Iterable[Finding]) -> Tuple[str, ...]:
    return tuple(f.rule_id for f in findings)
