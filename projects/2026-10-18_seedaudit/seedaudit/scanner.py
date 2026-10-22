"""Scanner: open Python file(s), analyze, run rules, roll up verdict."""

from __future__ import annotations

import os
from typing import Iterable

from .analyzer import analyze
from .rules import run_all
from .types import Finding, Options, ScanResult, Severity, Verdict
from .verdict import compute_verdict


def _is_python(name: str) -> bool:
    return name.endswith(".py")


def scan_text(content: str, path: str, options: Options) -> ScanResult:
    result = analyze(content, path)
    if result.syntax_error is not None:
        return ScanResult(
            findings=[Finding(
                rule_id="SEED-000",
                severity=Severity.MEDIUM,
                message="cannot parse Python source: " + result.syntax_error,
                subject=path,
                line=0,
                path=path,
            )],
            files_scanned=0,
            calls_scanned=0,
            verdict=Verdict.UNKNOWN,
            error=result.syntax_error,
        )
    findings = run_all(result, path, options)
    r = ScanResult(
        findings=findings,
        files_scanned=1,
        calls_scanned=len(result.calls),
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
                rule_id="SEED-000",
                severity=Severity.HIGH,
                message="cannot read file: " + str(e),
                subject="",
                line=0,
                path=path,
            )],
            files_scanned=0,
            calls_scanned=0,
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
                    if _is_python(full):
                        r = scan_file(full, options)
                        merged.findings.extend(r.findings)
                        merged.files_scanned += r.files_scanned
                        merged.calls_scanned += r.calls_scanned
        else:
            r = scan_file(p, options)
            merged.findings.extend(r.findings)
            merged.files_scanned += r.files_scanned
            merged.calls_scanned += r.calls_scanned
    merged.verdict = compute_verdict(
        merged.findings, merged.files_scanned, options,
    )
    merged.findings.sort(key=lambda f: (f.path, f.line, f.rule_id))
    return merged


__all__ = ["scan_text", "scan_file", "scan_paths"]
