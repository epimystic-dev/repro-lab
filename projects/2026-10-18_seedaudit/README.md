# seedaudit

> **AST-based linter** for Python code: flags random-number-generator calls
> that run without a seeding call in scope. Zero third-party dependencies.

## Why this exists

The most common cause of non-reproducible ML runs is a seed that is **declared
somewhere but never applied to the randomization point**. Three documented
2026 incidents make the pattern concrete:

- `aidotse/LeakPro` [PR #451](https://github.com/aidotse/LeakPro/pull/451)
  retrofitted a `random_seed` field that had been in the audit schema but
  consumed nowhere.
- A protein-folding reproducibility audit reported `src/experiment.py` using
  `np.random.normal(...)` and `train_test_split(...)` without seeds, while
  `config.yaml` set `random_seed: null`.
- `lmstudio-ai/mlx-engine` [issue #379](https://github.com/lmstudio-ai/mlx-engine/issues/379)
  documented a `seed` parameter silently ignored on the batched path.

The pattern is always the same: a seed is declared but the function that
samples never saw it. `seedaudit` walks Python source with the standard
library `ast` module and flags every call to a known RNG function that
occurs without a seeding call or a `seed=` / `random_state=` / `generator=`
keyword in scope.

## What it checks

Seven rules, every one grounded in public documentation:

| Rule | Severity | What it flags | Public source |
|---|---|---|---|
| SEED-001 | MEDIUM | stdlib `random.*` call with no `random.seed` in scope and no `seed=` kwarg | Python stdlib `random` docs |
| SEED-002 | MEDIUM | `numpy.random.*` call with no `numpy.random.seed` in scope and no `seed=` kwarg | NumPy `numpy.random` docs |
| SEED-003 | MEDIUM | `torch.*` sampling call with no `torch.manual_seed` in scope and no `generator=` | PyTorch `torch.manual_seed` docs |
| SEED-004 | MEDIUM | `tf.random.*` call with no `tf.random.set_seed` in scope and no `seed=` | TensorFlow `tf.random` docs |
| SEED-005 | **HIGH** | scikit-learn `train_test_split` / `KFold` / `shuffle` / `resample` without `random_state` | scikit-learn docs |
| SEED-006 | INFO | reseeding inside a function (seeding call appears more than once in the same scope) | reproducibility practice |
| SEED-007 | INFO | a seeding call is present but no RNG sampling call fires in this module | reproducibility practice |

### Framework coverage

`seedaudit` resolves import aliases, so `import numpy as np`,
`from numpy import random as nr`, and `from sklearn.model_selection import
train_test_split` all resolve to their canonical dotted names. The
canonical lists are maintained in `seedaudit/analyzer.py` and are grounded
in each framework's public documentation.

## Install and run

Python 3.9 or later. No third-party dependencies.

```
python -m pip install -e .
python -m seedaudit path/to/script.py
python -m seedaudit --json path/to/project/
python -m seedaudit --include-info path/to/script.py  # surface SEED-006, SEED-007
python -m seedaudit --disable SEED-002 path/to/script.py
```

Passed a directory, `seedaudit` recursively scans every `*.py` file.

### Exit codes

- `0` - healthy
- `1` - needs attention (MEDIUM only, or no files read)
- `2` - unhealthy (any HIGH finding - typically SEED-005) or unreadable input

## Honest scope

**What this tool does:**
- Walks the Python AST, resolves import aliases, and flags unseeded RNG
  calls per the rule table above.
- Treats `seed=`, `random_state=`, `generator=`, and `rng=` keyword
  arguments on a sampling call as evidence that the call is locally
  seeded.
- Treats any seeding call in the enclosing function OR the module as
  "in scope" for subsequent calls in the same file.

**What this tool does NOT do:**
- It does not run the code. If a seed is loaded dynamically from a YAML
  file at runtime and passed into a sampling call, we have no way to
  know. The code paths look unseeded to the analyzer.
- It does not track seeds across modules. A seed set in `conftest.py`
  that influences a sampling call in `train.py` will produce a false
  positive in `train.py` alone - run `seedaudit` on the whole package.
- It does not understand method-level RNG state (e.g. a `Generator`
  object passed in as a parameter). Callers may want to pass
  `--disable SEED-002` for code that uses `numpy.random.default_rng`
  objects throughout.
- It does not check whether a `random_state=42` is actually *the same*
  across runs - a shared integer constant is still origin-valid.

**Known false-positive modes:**
- Dynamic seed loading (`seed = int(os.environ["SEED"])` followed by
  `np.random.seed(seed)`) is detected only when the call appears in the
  same module.
- `scipy.stats.*` sampling calls are NOT in the canonical list, so they
  are not currently checked. (This is a documented limitation; scipy's
  `rvs` methods carry `random_state` of their own.)
- Fixture or test code that intentionally uses an unseeded RNG will
  trip. Use `--disable SEED-002` or restructure the test.

A clean run is **origin-valid, not verified-safe**.

## Clean-room

Rules are derived from the public documentation of the Python stdlib
`random` module, NumPy `numpy.random` (Generator and legacy global API),
PyTorch `torch.manual_seed`/`torch.random`, TensorFlow `tf.random`,
scikit-learn `train_test_split` and `shuffle` (the `random_state`
parameter), and the public Python `ast` module documentation.
**No reference implementation of any seed-checker, lint rule plugin
(Ruff, Flake8 extensions), or reproducibility scanner was read, vendored,
or mirrored.** This is an independent implementation and is not
affiliated with or endorsed by the authors of any such tool.

## License

MIT. See [LICENSE](LICENSE).

---

*Produced by Epimystic, a human-machine hybrid intelligence, under
maker-checker.*
