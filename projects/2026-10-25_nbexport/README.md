# nbexport

> Lint Jupyter notebooks for execution-order defects, and optionally
> emit a `.py` script in **linear** (file-order) or **executed**
> (recorded `execution_count` order) form. Zero network, zero
> third-party dependencies, standard library only.

## Why this exists

Jupyter notebooks permit out-of-order cell execution. The convenience
is real; the cost is that notebooks silently accumulate hidden state
and implicit dependencies, and a notebook that works in the author's
interactive session often fails under 'Restart and Run All'.

Three 2026 arXiv studies make the signal unambiguous:

- A survey of GitHub notebooks found only ~24% were fully executable
  top-to-bottom, and even after manual troubleshooting only ~11% of
  one studied sample became reproducible (*A Study of Scientific
  Computational Notebook Quality*, arXiv 2603.22726).
- FlowBook (arXiv 2605.01560) demonstrates that out-of-order execution
  is the root cause of a dominant share of silent reproducibility
  failures, evaluated against 61 Kaggle competition notebooks.
- JunoBench (arXiv 2510.18013), a crash-root-cause corpus of ML
  notebooks, attributes 74.3% of Kaggle notebook-specific crashes to
  cells being executed in an incorrect sequence.

Every one of those defects leaves a fingerprint in the file. `nbexport`
is nine shape-level offline checks against that fingerprint, plus a
script exporter that gives the reviewer the two orderings they actually
need: the top-to-bottom story the author claims, and the recorded
execution the kernel actually saw.

A clean run means the notebook's execution record is internally
consistent against the named checklist. It does **not** guarantee that
a top-to-bottom execution would succeed or produce the recorded
outputs.

## What it checks

Nine rules, every one citing a public source:

| Rule | Severity | What it flags | Public source |
|---|---|---|---|
| NBX-001 | HIGH | code cell has `execution_count=null` but sits between executed cells (never-run cell wedged in) | FlowBook (arXiv 2605.01560) |
| NBX-002 | HIGH | execution_count values are not monotonically increasing in file order (out-of-order execution) | FlowBook (arXiv 2605.01560) |
| NBX-003 | MEDIUM | the same execution_count appears on two code cells | nbformat v4 schema |
| NBX-004 | INFO | gap(s) in the execution_count sequence (cells deleted after being run) | nbformat v4 schema |
| NBX-005 | MEDIUM | cell contains `%` line magic or `!` shell command lines (replay under plain Python will not run them) | FlowBook (arXiv 2605.01560) |
| NBX-006 | MEDIUM | a name used in an earlier-executed cell is first introduced in a later-executed cell (import-after-use) | FlowBook (arXiv 2605.01560) |
| NBX-007 | MEDIUM | notebook metadata has no `kernelspec.name` | nbformat v4 schema |
| NBX-008 | INFO | notebook `language_info.name` is not Python | nbformat v4 schema |
| NBX-009 | HIGH | cell has `execution_count` set but empty source (cleared after execution) | nbformat v4 schema |

## Install and run

Python 3.9 or later. No third-party dependencies.

```
python -m pip install -e .

# lint
python -m nbexport path/to/notebook.ipynb
python -m nbexport --json path/to/notebook.ipynb > findings.json
python -m nbexport --disable NBX-005 path/to/notebook.ipynb

# emit a script
python -m nbexport --emit-script linear   path/to/notebook.ipynb -o nb_linear.py
python -m nbexport --emit-script executed path/to/notebook.ipynb -o nb_executed.py
```

Passed a directory, `nbexport` recursively scans files with the `.ipynb`
extension. `--emit-script` requires an explicit file path (not a
directory) so a reader never gets a silent fan-out.

### Exit codes

Per the lab-wide CLI contract:

| rc | meaning |
|---|---|
| 0 | `healthy`: no HIGH, no MEDIUM, no INFO above threshold |
| 1 | `needs-attention`: MEDIUM finding(s), or INFO under `--strict`, or no file read (unknown) |
| 2 | `unhealthy`: HIGH finding(s), or an unknown flag, or `--strict` + unknown |

Findings go to **stdout**; errors and `--help` go to **stderr**, so a
pipe reader can trust the stdout schema.

## Script emission modes

Both modes write a self-contained Python file with per-cell banners
and the originating `execution_count` noted:

- `--emit-script linear` writes cells in **file order**. This is what
  a reviewer wants when the question is "what does the author claim
  this notebook does?" If the notebook contains out-of-order execution,
  this script will often fail to run - that is the signal.
- `--emit-script executed` writes cells sorted by **recorded
  execution_count**. This is what a reviewer wants when the question
  is "what did the kernel see at the time the recorded outputs were
  produced?" Cells with `execution_count=null` are placed at the end,
  with a comment banner, in file order.

Line magics (`%...`) and shell commands (`!...`) are preserved as
`# nbexport: %...` / `# nbexport: !...` comments rather than emitted
raw, so the exported script runs under plain Python without ambiguity.

## Honest scope

What this tool does **not** do:

- It does not execute the notebook. It reads the record only.
- NBX-006 (import-after-use) uses a simple heuristic over imports and
  top-level assignments; attribute uses deep inside a function body
  may not be caught, and dynamic imports via `importlib` definitely
  are not. The rule aims at the common pattern (`import X` in a cell
  executed after `X.foo()` in an earlier cell).
- NBX-005 flags the presence of magics / shell lines, not whether they
  are correctly isolated.
- The `executed` emit mode cannot reconstruct what the kernel saw if
  the author re-ran a cell with the same `execution_count` multiple
  times - the record only preserves the latest state.

False-positive modes to know about:

- A notebook using a non-Python language will trip NBX-008 under
  `--strict`. Use `--disable NBX-008` for an R or Julia notebook.
- A notebook using `IPython`-only idioms (`display`, `?help`) will
  look fine under NBX-005 (those are not `%` or `!` prefixed) and will
  break on plain-Python replay. The gap is honest: NBX-005 catches
  what it mechanically can, not what it morally should.

## Clean-room provenance

Field names and shape semantics are derived from the public **nbformat
v4** schema (jupyter.org/nbformat). The defect taxonomy is paraphrased
from the three arXiv studies cited above. No reference implementation
of `nbconvert`, `jupytext`, `papermill`, or any similar tool was read,
vendored, or mirrored. This tool is an independent implementation and
is **not affiliated with or endorsed by** Project Jupyter.

## Development

```
python -m unittest discover -s tests
```

(No arguments beyond those. The lab's CI runs exactly this command from
the project directory; `project.json`'s `test_cmd` declares the same
string.)

Tests write scratch files into `.pytest_tmp/`, which is dot-prefixed and
git-ignored.

## License

MIT. See `LICENSE`.

---

*Produced by Epimystic, a human-machine hybrid intelligence, under
maker-checker.*
