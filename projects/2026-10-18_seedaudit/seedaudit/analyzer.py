"""AST analyzer for seedaudit.

Walks a Python module's AST, builds an import-alias map (so that
``import numpy as np`` and ``from numpy import random as nr`` are
resolved), and for every call site decides:

  * is this a known seeding call? (``random.seed``, ``np.random.seed``,
    ``torch.manual_seed``, ``tf.random.set_seed``, etc.)
  * is this a known RNG sampling call?
  * if the sampling call carries a ``seed=`` / ``random_state=`` /
    ``generator=`` keyword, treat it as locally seeded.

The analyzer returns ``AnalysisResult`` which the rule module then
consumes. The analyzer is pure (does not emit findings itself); rules
are also pure. This separation is deliberate so a user can write a
custom rule without re-walking the tree.

Public documentation sources (paraphrased, not quoted beyond the
fifteen-word limit):

  * Python stdlib ``random`` module - names of sampling functions and
    ``random.seed``.
  * NumPy ``numpy.random`` - the legacy global API (``np.random.seed``,
    ``np.random.rand``, ``np.random.randn``, ``np.random.randint``,
    ``np.random.choice``, ``np.random.shuffle``, ``np.random.permutation``)
    and the modern ``default_rng`` factory.
  * PyTorch ``torch.manual_seed`` and sampling functions
    (``torch.rand``, ``torch.randn``, ``torch.randint``, etc.).
  * TensorFlow ``tf.random.set_seed`` and ``tf.random.*``.
  * scikit-learn splitters and ``shuffle``/``resample`` carry a
    ``random_state`` parameter.
  * Python ``ast`` module.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Known names. The analyzer resolves aliases, then matches against these
# canonical dotted paths.
# ---------------------------------------------------------------------------

# Canonical seeding calls - a call to any one of these establishes a
# "seeded" context for the enclosing scope.
SEEDING_CALLS: Set[str] = {
    "random.seed",
    "numpy.random.seed",
    "numpy.random.default_rng",
    "torch.manual_seed",
    "torch.cuda.manual_seed",
    "torch.cuda.manual_seed_all",
    "tensorflow.random.set_seed",
    "tensorflow.set_random_seed",
    "jax.random.PRNGKey",
    "jax.random.key",
}

# Canonical RNG sampling calls grouped by framework. Framework key names
# are used in rule messages.
STDLIB_RNG: Set[str] = {
    "random.random",
    "random.uniform",
    "random.randint",
    "random.randrange",
    "random.choice",
    "random.choices",
    "random.sample",
    "random.shuffle",
    "random.gauss",
    "random.normalvariate",
    "random.triangular",
    "random.betavariate",
    "random.expovariate",
    "random.gammavariate",
    "random.lognormvariate",
    "random.vonmisesvariate",
    "random.paretovariate",
    "random.weibullvariate",
}

NUMPY_RNG: Set[str] = {
    "numpy.random.rand",
    "numpy.random.randn",
    "numpy.random.randint",
    "numpy.random.choice",
    "numpy.random.permutation",
    "numpy.random.shuffle",
    "numpy.random.random",
    "numpy.random.random_sample",
    "numpy.random.uniform",
    "numpy.random.normal",
    "numpy.random.standard_normal",
    "numpy.random.beta",
    "numpy.random.binomial",
    "numpy.random.gamma",
    "numpy.random.poisson",
    "numpy.random.exponential",
    "numpy.random.multinomial",
}

TORCH_RNG: Set[str] = {
    "torch.rand",
    "torch.randn",
    "torch.randint",
    "torch.randperm",
    "torch.multinomial",
    "torch.bernoulli",
    "torch.normal",
    "torch.poisson",
}

TF_RNG: Set[str] = {
    "tensorflow.random.uniform",
    "tensorflow.random.normal",
    "tensorflow.random.shuffle",
    "tensorflow.random.categorical",
    "tensorflow.random.poisson",
}

# scikit-learn calls that carry an authoritative ``random_state`` kwarg.
# These are intentionally HIGH severity - an ML pipeline without a split
# seed is the single most common reproducibility defect in the wild.
SKLEARN_SPLIT: Set[str] = {
    "sklearn.model_selection.train_test_split",
    "sklearn.model_selection.KFold",
    "sklearn.model_selection.StratifiedKFold",
    "sklearn.model_selection.ShuffleSplit",
    "sklearn.model_selection.StratifiedShuffleSplit",
    "sklearn.model_selection.GroupKFold",
    "sklearn.model_selection.GroupShuffleSplit",
    "sklearn.model_selection.StratifiedGroupKFold",
    "sklearn.model_selection.RepeatedKFold",
    "sklearn.model_selection.RepeatedStratifiedKFold",
    "sklearn.utils.shuffle",
    "sklearn.utils.resample",
}

ALL_RNG = (
    STDLIB_RNG | NUMPY_RNG | TORCH_RNG | TF_RNG | SKLEARN_SPLIT
)

# Keywords on RNG calls that locally seed the result (so the call does
# not require a global seed to be reproducible). These are the public,
# documented keyword names.
SEEDING_KWARGS: Set[str] = {
    "seed", "random_state", "generator", "rng",
}

# Framework label by dotted prefix - used in rule messages.
FRAMEWORK_OF: List[Tuple[str, str]] = [
    ("sklearn.", "scikit-learn"),
    ("numpy.", "numpy"),
    ("torch.", "torch"),
    ("tensorflow.", "tensorflow"),
    ("jax.", "jax"),
    ("random.", "stdlib random"),
]


def framework_of(dotted: str) -> str:
    for prefix, label in FRAMEWORK_OF:
        if dotted.startswith(prefix):
            return label
    return "unknown"


# ---------------------------------------------------------------------------
# Shape results returned by the analyzer.
# ---------------------------------------------------------------------------

@dataclass
class CallSite:
    dotted: str
    line: int
    col: int
    has_seeding_kwarg: bool
    scope_name: str
    scope_seeded: bool
    # True if a reseed happened in the SAME function before this call.
    reseeded_mid_function: bool = False


@dataclass
class SeedingSite:
    dotted: str
    line: int
    col: int
    scope_name: str
    is_module_level: bool


@dataclass
class AnalysisResult:
    """What the AST walk produces for one source file."""
    calls: List[CallSite] = field(default_factory=list)
    seeding_sites: List[SeedingSite] = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)
    syntax_error: Optional[str] = None


# ---------------------------------------------------------------------------
# Alias resolution.
# ---------------------------------------------------------------------------

def _resolve_dotted(node: ast.AST, aliases: Dict[str, str]) -> Optional[str]:
    """Attempt to resolve an attribute/name chain to its canonical dotted
    path using the alias map. Returns None if the chain can't be reduced
    to a flat dotted name.
    """
    parts: List[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    else:
        return None
    parts.reverse()
    if not parts:
        return None
    head = parts[0]
    if head in aliases:
        head_canonical = aliases[head]
        if len(parts) == 1:
            return head_canonical
        return head_canonical + "." + ".".join(parts[1:])
    return ".".join(parts)


def _collect_aliases(tree: ast.AST) -> Dict[str, str]:
    """Walk imports once to build name->canonical-dotted-path.

    Handles:
      import numpy                       -> numpy -> numpy
      import numpy as np                 -> np -> numpy
      from numpy import random           -> random -> numpy.random
      from numpy import random as nr     -> nr -> numpy.random
      from numpy.random import default_rng -> default_rng -> numpy.random.default_rng
    """
    aliases: Dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for alias in n.names:
                local = alias.asname if alias.asname else alias.name.split(".")[0]
                # For "import a.b" without asname, local is "a" and resolves to "a".
                if alias.asname:
                    aliases[local] = alias.name
                else:
                    aliases[local] = alias.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom):
            if n.module is None:
                continue
            for alias in n.names:
                local = alias.asname if alias.asname else alias.name
                aliases[local] = n.module + "." + alias.name
    return aliases


# ---------------------------------------------------------------------------
# Scope walker.
# ---------------------------------------------------------------------------

@dataclass
class _Scope:
    name: str
    is_module: bool
    seeded: bool = False
    reseed_count: int = 0


class _Walker(ast.NodeVisitor):
    def __init__(self, aliases: Dict[str, str]):
        self.aliases = aliases
        self.calls: List[CallSite] = []
        self.seeds: List[SeedingSite] = []
        self.scope_stack: List[_Scope] = [
            _Scope(name="<module>", is_module=True),
        ]

    # - Scope management -------------------------------------------------

    def _enter_function_scope(self, name: str) -> None:
        self.scope_stack.append(_Scope(name=name, is_module=False))

    def _exit_function_scope(self) -> None:
        self.scope_stack.pop()

    def _current_scope(self) -> _Scope:
        return self.scope_stack[-1]

    def _effectively_seeded(self) -> bool:
        """Function scope is seeded if the function OR the enclosing
        module has emitted a seeding call before this point.
        """
        # The module scope is always index 0.
        return any(s.seeded for s in self.scope_stack)

    # - Node visitors ----------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_function_scope(node.name)
        self.generic_visit(node)
        self._exit_function_scope()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_function_scope(node.name)
        self.generic_visit(node)
        self._exit_function_scope()

    def visit_Call(self, node: ast.Call) -> None:
        # Resolve the called expression.
        dotted = _resolve_dotted(node.func, self.aliases)
        if dotted is not None:
            if dotted in SEEDING_CALLS:
                scope = self._current_scope()
                if scope.seeded:
                    scope.reseed_count += 1
                scope.seeded = True
                self.seeds.append(SeedingSite(
                    dotted=dotted,
                    line=node.lineno,
                    col=node.col_offset,
                    scope_name=scope.name,
                    is_module_level=scope.is_module,
                ))
            elif dotted in ALL_RNG:
                has_kw = any(
                    (kw.arg is not None) and (kw.arg in SEEDING_KWARGS)
                    for kw in node.keywords
                )
                scope = self._current_scope()
                self.calls.append(CallSite(
                    dotted=dotted,
                    line=node.lineno,
                    col=node.col_offset,
                    has_seeding_kwarg=has_kw,
                    scope_name=scope.name,
                    scope_seeded=self._effectively_seeded(),
                    reseeded_mid_function=(
                        (not scope.is_module) and scope.reseed_count > 0
                    ),
                ))
        self.generic_visit(node)


def analyze(source: str, path: str = "<source>") -> AnalysisResult:
    """Parse ``source`` and return the AnalysisResult.

    A ``SyntaxError`` is captured in the result, not raised - so the
    caller can keep scanning other files in a batch.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return AnalysisResult(syntax_error=str(e))
    aliases = _collect_aliases(tree)
    w = _Walker(aliases)
    w.visit(tree)
    return AnalysisResult(
        calls=w.calls,
        seeding_sites=w.seeds,
        aliases=aliases,
    )


__all__ = [
    "CallSite",
    "SeedingSite",
    "AnalysisResult",
    "analyze",
    "framework_of",
    "SEEDING_CALLS",
    "STDLIB_RNG",
    "NUMPY_RNG",
    "TORCH_RNG",
    "TF_RNG",
    "SKLEARN_SPLIT",
    "ALL_RNG",
    "SEEDING_KWARGS",
]
