"""Shared test helpers for nbexport."""

from __future__ import annotations

import io
import json
import os
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from nbexport.cli import main as cli_main
from nbexport.rules import run_all
from nbexport.types import Finding, Options


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
_LOCAL_TMP = os.path.join(_PROJECT_ROOT, ".pytest_tmp")
os.makedirs(_LOCAL_TMP, exist_ok=True)
tempfile.tempdir = _LOCAL_TMP


def code_cell(
    source: str,
    execution_count: Optional[int] = 1,
    outputs: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": execution_count,
        "metadata": {},
        "outputs": outputs or [],
        "source": source if isinstance(source, list) else source.splitlines(
            keepends=True),
    }


def make_notebook(
    cells: Optional[List[Dict[str, Any]]] = None,
    kernel_name: str = "python3",
    language_name: str = "python",
) -> str:
    nb = {
        "cells": cells or [],
        "metadata": {
            "kernelspec": {"name": kernel_name, "display_name": kernel_name},
            "language_info": {"name": language_name},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(nb)


def scan_string(
    content: str,
    options: Optional[Options] = None,
    path: str = "in-memory.ipynb",
) -> Sequence[Finding]:
    options = options or Options(include_info=True)
    return run_all(content, path, options)


def write_temp(content: str, name: str = "sample.ipynb") -> Tuple[str, str]:
    d = tempfile.mkdtemp(prefix="nbexport_")
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
