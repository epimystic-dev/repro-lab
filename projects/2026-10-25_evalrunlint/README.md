# evalrunlint

> **Offline** comparability-reproducibility linter for evaluation-harness
> result files - `results.json`, `results.jsonl`, `details.json`. Zero
> network, zero third-party dependencies, standard library only.

## Why this exists

Two 2026 observations motivated this tool:

- `lm-evaluation-harness` v0.4.13 (EleutherAI) shipped fixes for a class
  of defects that had been silently corrupting published numbers: the
  few-shot sampler could draw the document under test into its own
  demonstrations; a scalar seed read from a config file was not
  normalized to the tuple form the harness expected; `gen_prefix` was
  resolved against the wrong document; and `enable_thinking=True` on
  multiple-choice tasks failed silently rather than being refused. Every
  one of those defects leaves a fingerprint in the written `results.json`
  that a shape-level linter can see.
- The LightEval configuration tracker records a sampling-param
  silent-drop class: `top_k`, `min_p`, `presence_penalty` are accepted
  by the config model but then not sent to the backend. Nothing in the
  resulting file flags that the run used different sampling than was
  requested. A linter that compares declared sampling against the
  sampling actually recorded on request-level entries catches this.

Beyond those specific bug classes, every published guide to
reproducibility (PromptLayer 2026; the EleutherAI README; the EvalPlus
README) agrees on a checklist that most published result files only
partially satisfy: a model pinned to an immutable revision; a seed set;
`--limit` off (or the record marked partial); one `num_fewshot` per
task; bootstrap iterations consistent with any confidence interval
reported; declared tasks all actually reported; a harness git-hash
captured.

`evalrunlint` is that checklist, as fifteen offline rules against the
files the harness actually writes.

A clean run means the record is **internally consistent and complete
against the named checklist**. It never means the reported numbers are
correct, or that the model would produce them on re-run.

## What it checks

Fifteen rules, every one citing its public source:

| Rule | Severity | What it flags | Public source |
|---|---|---|---|
| EVAL-001 | HIGH | result file has no model identifier at all | lm-eval-harness README |
| EVAL-002 | HIGH | model identifier is not pinned to an immutable revision | Hugging Face Hub revision docs |
| EVAL-003 | HIGH | `limit` is set and non-zero, but results are reported (partial run presented as full) | lm-eval-harness `--limit` docs |
| EVAL-004 | HIGH | `num_fewshot` differs across tasks on the same record | lm-eval-harness per-task fewshot config |
| EVAL-005 | MEDIUM | no seed field present anywhere on the record | lm-eval-harness `seed` / `random_seed` |
| EVAL-006 | HIGH | a field named `*_seeds` carries a scalar value instead of a list | lm-evaluation-harness v0.4.13 release notes |
| EVAL-007 | HIGH | a sampling param is declared in the config block but absent from the recorded requests (silent-drop) | huggingface/lighteval issue tracker |
| EVAL-008 | HIGH | the same task key appears more than once with different scores | lm-eval-harness task-registry duplicate detection |
| EVAL-009 | MEDIUM | a timestamp field has a year beyond `--current-year` | PromptLayer 2026 reproducibility checklist |
| EVAL-010 | MEDIUM | `stderr` / `ci_*` is present on a task but `bootstrap_iters` is zero or missing | lm-eval-harness `bootstrap_iters` docs |
| EVAL-011 | INFO | a task reports a score but `n_samples` is zero or negative | lm-eval-harness per-task n_samples recording |
| EVAL-012 | HIGH | the config declares N tasks but `results` reports fewer | lm-eval-harness task-selection docs |
| EVAL-013 | MEDIUM | `enable_thinking=True` combined with a multiple-choice task | lm-evaluation-harness v0.4.13 release notes |
| EVAL-014 | HIGH | a task has both a numeric score and an `error` / `traceback` field | lm-eval-harness task-level error recording |
| EVAL-015 | INFO | no `git_hash` / `harness_version` recorded on the record | lm-eval-harness `--log-samples` git_hash field |

## Install and run

Python 3.9 or later. No third-party dependencies.

```
python -m pip install -e .
python -m evalrunlint path/to/results.json
python -m evalrunlint --json path/to/results.json > findings.json
python -m evalrunlint --disable EVAL-015 path/to/results.json
python -m evalrunlint --current-year 2026 path/to/results.jsonl
```

Passed a directory, `evalrunlint` recursively scans files with the
extensions `.json` and `.jsonl`.

### Exit codes

Per the lab-wide CLI contract:

| rc | meaning |
|---|---|
| 0 | `healthy`: no HIGH, no MEDIUM, no INFO (or INFO is below the threshold) |
| 1 | `needs-attention`: MEDIUM finding(s), or INFO finding(s) under `--strict`, or no file read (unknown) |
| 2 | `unhealthy`: HIGH finding(s), or an unknown flag, or `--strict` + unknown |

`--json` writes a stable object to **stdout**; `--help` and errors go to
**stderr**, so a pipe reader can trust the stdout schema.

## Supported harness shapes

The parser recognizes the three main public formats and normalizes
them to a common record shape before rules run:

- **lm-evaluation-harness** `results.json` and `results.jsonl` - the
  top-level `results` / `configs` / `model` / `model_args` /
  `num_fewshot` / `seed` / `limit` / `bootstrap_iters` / `git_hash`
  keys.
- **EvalPlus** `results.json` - the `model` / `pass@1` / `n_samples`
  shape.
- **LightEval** `details.json` - the `sampling_params` /
  `requests` / `samples` nesting, so EVAL-007 can compare declared
  sampling against the sampling actually recorded on each request.

Anything the parser cannot classify is still returned with raw fields
preserved, and rules fire on whatever fields they can locate.

## Honest scope

What this tool does **not** do:

- It does not re-run the evaluation; it reads the record only.
- It does not check whether the model exists on any registry; EVAL-002
  only asks whether an immutable revision is recorded alongside the
  identifier.
- It does not score correctness of the reported numbers.
- It cannot see a few-shot leakage that was not written to the result
  file. The v0.4.13 fix changed the sampler, not the result-file
  schema; what EVAL-006 catches is the scalar-seed-in-tuple-slot bug
  class that the same release documents.
- EVAL-007 fires only when the record actually has a recorded
  `requests` / `samples` block to compare the config block against -
  harnesses that only write aggregate scores give no evidence of
  silence.

False-positive modes to know about:

- A result file that reports a task name identical to a multiple-choice
  benchmark but is actually a different task family will trip EVAL-013
  if `enable_thinking=True`. Use `--disable EVAL-013`.
- Harnesses that pin a model at the loader (outside the result file)
  will trip EVAL-002. Use `--disable EVAL-002` or declare the revision
  in the result file.
- Non-ISO timestamp formats whose first four characters happen to be
  digits but are not a year will not be caught; the rule is deliberately
  conservative.

## Clean-room provenance

The parser and rules were implemented against the public documentation
and release notes of the harnesses listed above. No reference
implementation of any evaluation harness was read, vendored, or
mirrored. This tool is an independent implementation and is **not
affiliated with or endorsed by** EleutherAI, Hugging Face, or the
EvalPlus authors.

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
