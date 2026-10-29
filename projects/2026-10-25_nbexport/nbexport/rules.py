"""Rule registry for nbexport.

Nine rules spanning execution-order consistency, cell-source
consistency, kernel/language metadata, and import-ordering across
executed cells. Rule IDs use the ``NBX-`` prefix.

Public spec sources paraphrased (never vendored):

  - nbformat v4 notebook schema (jupyter.org/nbformat docs): ``cells``,
    ``execution_count``, ``source``, ``metadata``, ``kernelspec``,
    ``language_info``.
  - 2026 arXiv findings on notebook reproducibility: FlowBook on
    out-of-order execution (arXiv 2605.01560); the GitHub study
    reporting 24% notebook executability; the Kaggle crash study
    (JunoBench) reporting 74.3% of notebook-specific crashes stem from
    out-of-order execution.

A clean run means the notebook's execution record is internally
consistent against the named checklist. It does **not** guarantee that
a top-to-bottom execution would succeed or produce the recorded
outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from .notebook import (
    CodeCell, Notebook, _BUILTINS, _declared_names, _referenced_names,
    parse_notebook,
)
from .types import Finding, Options, Severity


Check = Callable[[Notebook, Options, str], List[Finding]]


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    title: str
    description: str
    citation: str
    check: Check


_FLOWBOOK_CITE = (
    "FlowBook (arXiv 2605.01560, 2026) on out-of-order cell execution;"
    " JunoBench (arXiv 2510.18013) on Kaggle crash root causes"
)
_NBFORMAT_CITE = "nbformat v4 schema (jupyter.org/nbformat)"


def _null_between_executed(nb, options, path):
    out: List[Finding] = []
    executed_before = False
    executed_after = False
    first_null: int = -1
    for c in nb.code_cells:
        if c.execution_count is not None:
            if first_null >= 0 and executed_before:
                executed_after = True
            executed_before = True
    # First pass is a flag; the actual report is per-cell.
    cells = nb.code_cells
    for i, c in enumerate(cells):
        if c.execution_count is None and not c.is_empty():
            # Only count as a defect if there is at least one executed
            # cell before AND after this one.
            prev = any(x.execution_count is not None for x in cells[:i])
            later = any(x.execution_count is not None
                        for x in cells[i + 1:])
            if prev and later:
                out.append(Finding(
                    rule_id="NBX-001",
                    severity=Severity.HIGH,
                    message=("code cell has never been executed but sits"
                             " between executed cells"),
                    subject="cell[" + str(c.index) + "]",
                    line=0,
                    path=path,
                    hint=("either run this cell or delete it before"
                          " sharing the notebook"),
                    citation=_FLOWBOOK_CITE,
                ))
    return out


def _non_monotonic_execution(nb, options, path):
    out: List[Finding] = []
    last_ec = -1
    last_idx = -1
    for c in nb.code_cells:
        if c.execution_count is None:
            continue
        if c.execution_count < last_ec:
            out.append(Finding(
                rule_id="NBX-002",
                severity=Severity.HIGH,
                message=("execution_count is non-monotonic in file order"
                         " (cell[" + str(c.index) + "] has ec=" +
                         str(c.execution_count) + ", previous executed"
                         " cell had ec=" + str(last_ec) + ")"),
                subject="cell[" + str(c.index) + "]",
                line=0,
                path=path,
                hint=("re-run the notebook top-to-bottom with"
                      " 'Restart and Run All' before sharing"),
                citation=_FLOWBOOK_CITE,
            ))
        last_ec = c.execution_count
        last_idx = c.index
    return out


def _duplicate_execution_count(nb, options, path):
    out: List[Finding] = []
    seen: dict = {}
    for c in nb.code_cells:
        if c.execution_count is None:
            continue
        prev = seen.get(c.execution_count)
        if prev is not None:
            out.append(Finding(
                rule_id="NBX-003",
                severity=Severity.MEDIUM,
                message=("execution_count " + str(c.execution_count) +
                         " appears twice (cells " + str(prev) + " and " +
                         str(c.index) + ")"),
                subject="ec=" + str(c.execution_count),
                line=0,
                path=path,
                hint=("rerun top-to-bottom; duplicate counts come from"
                      " copy-paste or truncated kernels"),
                citation=_NBFORMAT_CITE,
            ))
        else:
            seen[c.execution_count] = c.index
    return out


def _execution_count_gaps(nb, options, path):
    out: List[Finding] = []
    executed = [c for c in nb.code_cells if c.execution_count is not None]
    if len(executed) < 2:
        return out
    counts = sorted({c.execution_count for c in executed})
    expected = set(range(counts[0], counts[-1] + 1))
    missing = sorted(expected - set(counts))
    if missing:
        out.append(Finding(
            rule_id="NBX-004",
            severity=Severity.INFO,
            message=("gap(s) in execution_count sequence: " +
                     ",".join(str(x) for x in missing[:5]) +
                     ("..." if len(missing) > 5 else "")),
            subject="execution_count",
            line=0,
            path=path,
            hint=("gaps are consistent with cells deleted after being"
                  " run; verify the deletion was intended"),
            citation=_NBFORMAT_CITE,
        ))
    return out


def _magic_or_shell(nb, options, path):
    out: List[Finding] = []
    for c in nb.code_cells:
        for lineno, line in enumerate(c.source.splitlines(), 1):
            stripped = line.lstrip()
            if not stripped:
                continue
            if stripped.startswith("%") or stripped.startswith("!"):
                prefix = stripped[0]
                out.append(Finding(
                    rule_id="NBX-005",
                    severity=Severity.MEDIUM,
                    message=("line " + str(lineno) + " of cell["
                             + str(c.index) + "] starts with '"
                             + prefix + "' (" +
                             ("line magic" if prefix == "%"
                              else "shell command") + ")"),
                    subject="cell[" + str(c.index) + "]:L" + str(lineno),
                    line=lineno,
                    path=path,
                    hint=("line magics and shell commands do not run under"
                          " plain Python; port to a stdlib equivalent or"
                          " isolate in a shell-only cell"),
                    citation=_FLOWBOOK_CITE,
                ))
                break  # one finding per cell is enough
    return out


def _import_after_use(nb, options, path):
    """Fire when a name is used in an executed cell before being
    imported in a later-executed cell. We only use executed cells so
    the signal is grounded in what the kernel actually saw.
    """
    out: List[Finding] = []
    executed = [c for c in nb.code_cells if c.execution_count is not None]
    if len(executed) < 2:
        return out
    order = sorted(executed, key=lambda c: c.execution_count or 0)
    seen: dict = {}  # name -> first execution_count where introduced
    for c in order:
        decl = set(_declared_names(c.source)) - _BUILTINS
        refs = set(_referenced_names(c.source)) - _BUILTINS
        # References first, so a cell that both uses and declares a
        # name (``import x; x.foo()``) is handled correctly.
        for name in sorted(refs):
            if name in _BUILTINS:
                continue
            if name in seen and seen[name] <= (c.execution_count or 0):
                continue
            # The name is referenced but not yet seen. Does a LATER
            # executed cell introduce it?
            for later in order:
                if later is c:
                    continue
                if (later.execution_count or 0) <= (c.execution_count or 0):
                    continue
                later_decl = set(_declared_names(later.source)) - _BUILTINS
                if name in later_decl:
                    out.append(Finding(
                        rule_id="NBX-006",
                        severity=Severity.MEDIUM,
                        message=("name '" + name + "' used in cell["
                                 + str(c.index) + "] (ec="
                                 + str(c.execution_count) +
                                 ") but first introduced in cell["
                                 + str(later.index) + "] (ec="
                                 + str(later.execution_count) + ")"),
                        subject=name,
                        line=0,
                        path=path,
                        hint=("rerun top-to-bottom; the kernel saw the"
                              " name only because the later cell was"
                              " run first"),
                        citation=_FLOWBOOK_CITE,
                    ))
                    break
        for name in decl:
            if name not in seen:
                seen[name] = c.execution_count or 0
    return out


def _missing_kernelspec(nb, options, path):
    if nb.kernel_name:
        return []
    return [Finding(
        rule_id="NBX-007",
        severity=Severity.MEDIUM,
        message="notebook metadata has no kernelspec.name",
        subject="metadata.kernelspec",
        line=0,
        path=path,
        hint=("record the kernel the notebook was last run under"),
        citation=_NBFORMAT_CITE,
    )]


def _non_python_language(nb, options, path):
    if not nb.language_name:
        return []
    if nb.language_name.lower() != "python":
        return [Finding(
            rule_id="NBX-008",
            severity=Severity.INFO,
            message=("notebook language_info.name is '" + nb.language_name
                     + "' (not Python); --emit-script writes Python only"),
            subject="metadata.language_info",
            line=0,
            path=path,
            hint=("use the notebook's native export; nbexport emits"
                  " Python"),
            citation=_NBFORMAT_CITE,
        )]
    return []


def _executed_but_empty(nb, options, path):
    out: List[Finding] = []
    for c in nb.code_cells:
        if c.execution_count is not None and c.is_empty():
            out.append(Finding(
                rule_id="NBX-009",
                severity=Severity.HIGH,
                message=("cell[" + str(c.index) +
                         "] has execution_count=" + str(c.execution_count)
                         + " but empty source (cleared after execution)"),
                subject="cell[" + str(c.index) + "]",
                line=0,
                path=path,
                hint=("delete the cell or restore its source"),
                citation=_NBFORMAT_CITE,
            ))
    return out


REGISTRY: List[Rule] = [
    Rule("NBX-001", Severity.HIGH,
         "never-run cell between executed cells",
         "code cell has execution_count=null but sits between executed"
         " cells",
         _FLOWBOOK_CITE,
         _null_between_executed),
    Rule("NBX-002", Severity.HIGH,
         "non-monotonic execution_count",
         "execution_count values are not monotonically increasing in"
         " file order",
         _FLOWBOOK_CITE,
         _non_monotonic_execution),
    Rule("NBX-003", Severity.MEDIUM,
         "duplicate execution_count",
         "the same execution_count appears on two code cells",
         _NBFORMAT_CITE,
         _duplicate_execution_count),
    Rule("NBX-004", Severity.INFO,
         "execution_count gaps",
         "cells were deleted after being executed, leaving numeric gaps",
         _NBFORMAT_CITE,
         _execution_count_gaps),
    Rule("NBX-005", Severity.MEDIUM,
         "line magic or shell command",
         "cell contains % or ! prefixed lines that will not run under"
         " plain Python",
         _FLOWBOOK_CITE,
         _magic_or_shell),
    Rule("NBX-006", Severity.MEDIUM,
         "import after use",
         "a name is used in an earlier-executed cell but first"
         " introduced in a later-executed cell",
         _FLOWBOOK_CITE,
         _import_after_use),
    Rule("NBX-007", Severity.MEDIUM,
         "missing kernelspec",
         "notebook metadata has no kernelspec.name",
         _NBFORMAT_CITE,
         _missing_kernelspec),
    Rule("NBX-008", Severity.INFO,
         "non-python language",
         "notebook language_info.name is not Python",
         _NBFORMAT_CITE,
         _non_python_language),
    Rule("NBX-009", Severity.HIGH,
         "executed cell with empty source",
         "cell has execution_count set but empty source (cleared after"
         " execution)",
         _NBFORMAT_CITE,
         _executed_but_empty),
]


def run_all(content: str, path: str, options: Options
            ) -> List[Finding]:
    nb = parse_notebook(content)
    out: List[Finding] = []
    if nb.parse_error:
        out.append(Finding(
            rule_id="NBX-000",
            severity=Severity.HIGH,
            message="could not parse notebook: " + nb.parse_error,
            subject="",
            line=0,
            path=path,
            hint="pass a .ipynb (nbformat v4) file",
            citation="",
        ))
        return out
    for rule in REGISTRY:
        if not options.rule_enabled(rule.id):
            continue
        if rule.severity is Severity.INFO and not (
                options.include_info or options.strict):
            continue
        out.extend(rule.check(nb, options, path))
    return out


__all__ = ["REGISTRY", "Rule", "Check", "run_all"]
