"""Rule registry for seedaudit.

Seven rules on the Python-source call surface, each citing the public
documentation it is grounded in. Rule IDs use the ``SEED-`` prefix; the
lab-wide shared surface exposes this list as ``ALL_RULES``.

A clean run means every known RNG call is either in a scope that saw a
seeding call, or carries an explicit ``seed`` / ``random_state`` /
``generator`` keyword. It never means the run itself will be
bit-identical across hardware or software versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from .analyzer import (
    ALL_RNG,
    NUMPY_RNG,
    SKLEARN_SPLIT,
    STDLIB_RNG,
    TF_RNG,
    TORCH_RNG,
    AnalysisResult,
    framework_of,
)
from .types import Finding, Options, Severity


Check = Callable[[AnalysisResult, str, Options], List[Finding]]


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    title: str
    description: str
    citation: str
    check: Check


# ---------------------------------------------------------------------------
# Framework-specific unseeded-call rules. The severity is HIGH for the
# scikit-learn split family (data-plumbing non-determinism breaks every
# downstream metric), MEDIUM for the general sampling families.
# ---------------------------------------------------------------------------

def _unseeded_calls_from(
    result: AnalysisResult,
    path: str,
    options: Options,
    accept: set,
    rule_id: str,
    severity: Severity,
    citation: str,
    hint: str,
) -> List[Finding]:
    findings: List[Finding] = []
    for call in result.calls:
        if call.dotted not in accept:
            continue
        if call.has_seeding_kwarg:
            continue
        if call.scope_seeded:
            continue
        findings.append(Finding(
            rule_id=rule_id,
            severity=severity,
            message=(
                framework_of(call.dotted)
                + " call '" + call.dotted
                + "' in scope '" + call.scope_name
                + "' has no seeding call in scope and no seed/random_state"
                " kwarg"
            ),
            subject=call.dotted,
            line=call.line,
            path=path,
            hint=hint,
            citation=citation,
        ))
    return findings


def _check_stdlib_unseeded(
    result: AnalysisResult, path: str, options: Options,
) -> List[Finding]:
    return _unseeded_calls_from(
        result, path, options,
        STDLIB_RNG,
        "SEED-001", Severity.MEDIUM,
        "Python stdlib random module docs",
        "Call random.seed(...) at module import or pass seed= explicitly.",
    )


def _check_numpy_unseeded(
    result: AnalysisResult, path: str, options: Options,
) -> List[Finding]:
    return _unseeded_calls_from(
        result, path, options,
        NUMPY_RNG,
        "SEED-002", Severity.MEDIUM,
        "NumPy numpy.random docs",
        "Call numpy.random.seed(...) or switch to numpy.random.default_rng(seed)"
        " and pass the Generator in explicitly.",
    )


def _check_torch_unseeded(
    result: AnalysisResult, path: str, options: Options,
) -> List[Finding]:
    return _unseeded_calls_from(
        result, path, options,
        TORCH_RNG,
        "SEED-003", Severity.MEDIUM,
        "PyTorch torch.manual_seed docs",
        "Call torch.manual_seed(...) before any sampling (also"
        " torch.cuda.manual_seed_all on multi-GPU).",
    )


def _check_tf_unseeded(
    result: AnalysisResult, path: str, options: Options,
) -> List[Finding]:
    return _unseeded_calls_from(
        result, path, options,
        TF_RNG,
        "SEED-004", Severity.MEDIUM,
        "TensorFlow tf.random docs",
        "Call tf.random.set_seed(...) before any sampling, or pass"
        " seed=... to the sampling call.",
    )


def _check_sklearn_split_unseeded(
    result: AnalysisResult, path: str, options: Options,
) -> List[Finding]:
    # Overriding severity: a train/test split without random_state is
    # the single most common reproducibility defect in the wild.
    findings: List[Finding] = []
    for call in result.calls:
        if call.dotted not in SKLEARN_SPLIT:
            continue
        if call.has_seeding_kwarg:
            continue
        # NOTE: scikit-learn splits do NOT inherit a global seed; the
        # scope_seeded signal is irrelevant here.
        findings.append(Finding(
            rule_id="SEED-005",
            severity=Severity.HIGH,
            message=(
                "scikit-learn call '" + call.dotted
                + "' in scope '" + call.scope_name
                + "' has no random_state keyword - splits will be"
                " non-deterministic across runs"
            ),
            subject=call.dotted,
            line=call.line,
            path=path,
            hint="Pass random_state=<int> explicitly on every split and"
                 " shuffle call.",
            citation="scikit-learn train_test_split / shuffle docs",
        ))
    return findings


def _check_reseed_mid_function(
    result: AnalysisResult, path: str, options: Options,
) -> List[Finding]:
    """SEED-006: reseeding inside a function (after a prior seed in the
    same function) is almost always a smell - it masks the entropy of
    the outer run or injects a per-call constant that defeats sampling
    diversity.
    """
    findings: List[Finding] = []
    # The reseed_count signal lives on the function scope. We approximate
    # by surfacing one finding per RNG call that observed a mid-function
    # reseed before it fired.
    seen_scopes: set = set()
    for call in result.calls:
        if not call.reseeded_mid_function:
            continue
        if call.scope_name in seen_scopes:
            continue
        seen_scopes.add(call.scope_name)
        findings.append(Finding(
            rule_id="SEED-006",
            severity=Severity.INFO,
            message=(
                "RNG call '" + call.dotted
                + "' observed a reseed earlier in function '"
                + call.scope_name
                + "' - repeated per-call reseeding is almost always"
                " a smell"
            ),
            subject=call.scope_name,
            line=call.line,
            path=path,
            hint="Seed once per run at module import, not per call.",
            citation="Reproducibility practice; see NumPy new RNG guide",
        ))
    return findings


def _check_seed_defined_but_unused(
    result: AnalysisResult, path: str, options: Options,
) -> List[Finding]:
    """SEED-007: a seeding call appeared in the module but no RNG call
    did. Usually a left-over from refactoring - the config declares a
    seed, nothing samples with it.
    """
    findings: List[Finding] = []
    if not result.seeding_sites:
        return findings
    rng_calls_in_file = [
        c for c in result.calls if c.dotted in ALL_RNG
    ]
    if rng_calls_in_file:
        return findings
    seed = result.seeding_sites[0]
    findings.append(Finding(
        rule_id="SEED-007",
        severity=Severity.INFO,
        message=(
            "seeding call '" + seed.dotted
            + "' is present but no RNG sampling call fires in this"
            " module"
        ),
        subject=seed.dotted,
        line=seed.line,
        path=path,
        hint="If this is a config file or test harness, ignore. If this"
             " is production code, the seed is dead.",
        citation="Reproducibility practice",
    ))
    return findings


# ---------------------------------------------------------------------------
# Registry.
# ---------------------------------------------------------------------------

REGISTRY: List[Rule] = [
    Rule("SEED-001", Severity.MEDIUM,
         "Unseeded stdlib random call",
         "A call to random.<fn> occurred without a random.seed in scope"
         " and without a seed= kwarg.",
         "Python stdlib random docs",
         _check_stdlib_unseeded),
    Rule("SEED-002", Severity.MEDIUM,
         "Unseeded numpy.random call",
         "A call to numpy.random.<fn> occurred without numpy.random.seed"
         " in scope and without a seed= kwarg.",
         "NumPy numpy.random docs",
         _check_numpy_unseeded),
    Rule("SEED-003", Severity.MEDIUM,
         "Unseeded torch sampling call",
         "A call to torch.<fn> occurred without torch.manual_seed in"
         " scope and without a generator= kwarg.",
         "PyTorch torch.manual_seed docs",
         _check_torch_unseeded),
    Rule("SEED-004", Severity.MEDIUM,
         "Unseeded tf.random call",
         "A call to tf.random.<fn> occurred without tf.random.set_seed"
         " in scope and without a seed= kwarg.",
         "TensorFlow tf.random docs",
         _check_tf_unseeded),
    Rule("SEED-005", Severity.HIGH,
         "scikit-learn split without random_state",
         "train_test_split / KFold / shuffle must carry random_state.",
         "scikit-learn train_test_split / shuffle docs",
         _check_sklearn_split_unseeded),
    Rule("SEED-006", Severity.INFO,
         "Reseed inside a function",
         "A seeding call appears more than once in the same function;"
         " repeated per-call reseeding is almost always a smell.",
         "Reproducibility practice",
         _check_reseed_mid_function),
    Rule("SEED-007", Severity.INFO,
         "Seed declared but never consumed",
         "A seeding call is present but no RNG sampling call fires in"
         " this module.",
         "Reproducibility practice",
         _check_seed_defined_but_unused),
]


def _run_check_once(
    check: Check,
    result: AnalysisResult,
    path: str,
    options: Options,
) -> List[Finding]:
    out: List[Finding] = []
    for f in check(result, path, options):
        if not options.rule_enabled(f.rule_id):
            continue
        if f.severity is Severity.INFO and not (
            options.include_info or options.strict
        ):
            continue
        out.append(f)
    return out


def run_all(
    result: AnalysisResult, path: str, options: Options,
) -> List[Finding]:
    seen: set = set()
    findings: List[Finding] = []
    for rule in REGISTRY:
        if rule.check in seen:
            continue
        seen.add(rule.check)
        findings.extend(_run_check_once(rule.check, result, path, options))
    return findings


__all__ = [
    "Check",
    "Rule",
    "REGISTRY",
    "run_all",
]
