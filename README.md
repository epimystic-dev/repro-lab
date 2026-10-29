# repro-lab

Tools for research reproducibility and evaluation integrity: whether a reported result can be re-derived from what was published.

> Part of [Epimystic](https://epimystic.com) - a codex of the knowable and the unknowable.
> One of a family of labs: [`epimystic-lab`](https://github.com/epimystic-dev/epimystic-lab) / [`governance-lab`](https://github.com/epimystic-dev/governance-lab) / [`defense-lab`](https://github.com/epimystic-dev/defense-lab) / [`repro-lab`](https://github.com/epimystic-dev/repro-lab) / [`agent-guard-lab`](https://github.com/epimystic-dev/agent-guard-lab) / [`ai-ethics-lab`](https://github.com/epimystic-dev/ai-ethics-lab) / [`convergent-disciplines-lab`](https://github.com/epimystic-dev/convergent-disciplines-lab).

## What this is

A governed human-machine process scans the frontier each week and, *when something is
genuinely worth building*, produces one small, self-contained, tested artifact here. When
nothing clears the bar, it ships nothing but the radar entry - restraint is the quality gate.

- **`projects/`** - dated, self-contained micro-projects, each independently licensed,
  tested and documented.
- **`research-radar/`** - a dated digest of frontier signal: a few items each week with a
  one-line "why this matters", cited to source, and a note on what was built and why.

## What belongs here

Tools that ask one question of a research artifact: can the reported result be re-derived
from what was published? Linters and utilities over the files research actually produces -
evaluation-result files, experiment configs, dataset and model cards, split definitions,
notebooks, bibliographies, lockfiles, figures - reporting what is missing, inconsistent,
leaked or unpinned. These tools check the *record* of an experiment, never re-run it, and a
passing check means the record is complete and consistent against a named checklist, not
that the result is correct.

## The tools currently published

Each folder has its own README, tests and LICENSE; click through for install and usage.

| Tool | What it does | Layer |
|---|---|---|
| [doicheck](projects/2026-10-18_doicheck/) | Offline linter for DOI, arXiv, ORCID, and ISBN identifiers plus BibTeX hygiene - zero network, zero dependencies. | linter |
| [seedaudit](projects/2026-10-18_seedaudit/) | AST-based linter for Python code: flags RNG calls that run without a seeding call in scope. | linter |
| [evalrunlint](projects/2026-10-25_evalrunlint/) | Offline comparability linter for evaluation-harness result files (lm-eval-harness, EvalPlus, LightEval) - unpinned models, missing seeds, partial runs, silent-drop sampling, and more. | linter |
| [nbexport](projects/2026-10-25_nbexport/) | Lint Jupyter notebooks for execution-order defects and emit a .py script in linear or recorded execution order. | cli |

*The radar publishes every Monday; artifacts land across the week.*

## How it is made (and what that means)

Every artifact here is produced by **a human-machine hybrid intelligence, rooted in ethics
and philosophy**, and passes - *before* it is published - an external, deterministic policy
gate and an independent maker-checker review: a de-brand / secret gate, a clean-room rule (a
paper's method is read, never the authors' code), tests green under the public CI command,
and a claims-substantiation pass. The gate runs *outside* the builder. A passing gate means
**origin-valid, content-unverified**, never **verified-safe**. The engineering contract every
project meets is in [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md).

## Honest scope

This is a research-and-utility lab, not a product. Artifacts are small by design;
reimplementations of published work are independent implementations, cited and **not
affiliated with or endorsed by the original authors**. Read each project's own README and
LICENSE.

## License

Each `projects/` artifact carries its own LICENSE (permissive; this lab's default is
MIT). The radar and this index are MIT.

---

*Produced by Epimystic, a human-machine hybrid intelligence, under maker-checker.*
