"""Scanner: open file(s), run rules, roll up verdict."""

from __future__ import annotations

import os
from typing import Iterable

from .parser import parse_file
from .rules import run_all
from .types import Finding, Options, ScanResult, Severity, Verdict
from .verdict import compute_verdict


_PLAUSIBLE_EXTS = (".json", ".jsonl")


def _plausible(name: str) -> bool:
    base = os.path.basename(name).lower()
    return any(base.endswith(ext) for ext in _PLAUSIBLE_EXTS)


def scan_text(content: str, path: str, options: Options) -> ScanResult:
    findings = run_all(content, path, options)
    records, _err = parse_file(content)
    r = ScanResult(
        findings=findings,
        files_scanned=1,
        records_scanned=len(records),
    )
    r.verdict = compute_verdict(findings, r.files_scanned, options)
    return r


def scan_file(path: str, options: Options) -> ScanResult:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return ScanResult(
            findings=[Finding(
                rule_id="EVAL-000",
                severity=Severity.HIGH,
                message="cannot read file: " + str(e),
                subject="",
                line=0,
                path=path,
                hint="",
                citation="",
            )],
            files_scanned=0,
            records_scanned=0,
            verdict=Verdict.UNHEALTHY,
            error=str(e),
        )
    return scan_text(content, path, options)


def scan_paths(paths: Iterable[str], options: Options) -> ScanResult:
    merged = ScanResult()
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for name in files:
                    full = os.path.join(root, name)
                    if _plausible(full):
                        r = scan_file(full, options)
                        merged.findings.extend(r.findings)
                        merged.files_scanned += r.files_scanned
                        merged.records_scanned += r.records_scanned
        else:
            r = scan_file(p, options)
            merged.findings.extend(r.findings)
            merged.files_scanned += r.files_scanned
            merged.records_scanned += r.records_scanned
    merged.verdict = compute_verdict(
        merged.findings, merged.files_scanned, options,
    )
    merged.findings.sort(key=lambda f: (f.path, f.line, f.rule_id))
    return merged


__all__ = ["scan_text", "scan_file", "scan_paths"]
