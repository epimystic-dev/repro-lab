# doicheck

> **Offline** linter for DOI, arXiv, ORCID, and ISBN identifiers plus BibTeX
> hygiene. Zero network, zero third-party dependencies, standard library only.

## Why this exists

Scholarly artifacts fail reproducibility at the citation layer long before
they fail at the data layer. The 2026 wave of hallucinated-reference work
(doi-checker at ACM; BibTeX Verifier; CheckIfExist, arXiv 2602.15871;
HALLMARK, arXiv 2607.18360) has produced several good tools - but every one
of them resolves identifiers against a live registry at scan time, which
rules them out of offline CI, pre-commit hooks, and air-gapped research
environments.

`doicheck` checks what can be checked without a network: format against the
public spec, and checksum where one is defined. A clean run means the record
is well-formed and internally consistent against the named checklist; it
**never** means the identifiers resolve or that the cited work exists.

## What it checks

Fifteen rules, every one citing its public source:

| Rule | Severity | What it flags | Public source |
|---|---|---|---|
| DOI-001 | HIGH | DOI prefix not `10.<digits>[.<digits>...]` | DOI Handbook 2.5.1 |
| DOI-002 | HIGH | DOI missing `/` or empty suffix | DOI Handbook 2.5.1 |
| DOI-003 | MEDIUM | DOI contains whitespace or ASCII control chars | DOI Handbook 2.5.1 |
| DOI-004 | HIGH | arXiv ID matches neither new-style nor old-style format | arXiv identifier scheme |
| DOI-005 | MEDIUM | arXiv ID month is implausible or year is in the future | arXiv identifier scheme |
| DOI-006 | HIGH | ORCID failed ISO 7064 Mod 11,2 checksum | ORCID support |
| DOI-007 | HIGH | ORCID shape not 4-4-4-4 digits (+ optional X) | ORCID support |
| DOI-008 | HIGH | ISBN-10 failed mod-11 checksum | ISO 2108 |
| DOI-009 | HIGH | ISBN-13 failed mod-10 checksum | ISO 2108 |
| DOI-010 | MEDIUM | BibTeX entry missing a required field for its type | BibTeX user's guide |
| DOI-011 | MEDIUM | BibTeX entry year is in the future | 2026 hallucination studies |
| DOI-012 | MEDIUM | BibTeX field has an empty value | BibTeX user's guide |
| DOI-013 | HIGH | Duplicate BibTeX cite key | BibTeX user's guide |
| DOI-014 | MEDIUM | BibTeX field has unbalanced braces | BibTeX user's guide |
| DOI-015 | HIGH | BibTeX `doi` / `eprint` / `isbn` field is not a well-formed identifier | combined |

## Install and run

Python 3.9 or later. No third-party dependencies.

```
python -m pip install -e .
python -m doicheck path/to/references.bib
python -m doicheck --json path/to/references.bib > findings.json
python -m doicheck --disable DOI-003 path/to/references.bib
python -m doicheck --current-year 2026 path/to/references.bib
```

Passed a directory, `doicheck` recursively scans files with the extensions
`.bib`, `.bibtex`, `.tex`, `.txt`, `.md`, and `.rst`.

### Exit codes

Per the lab-wide CLI contract:

- `0` - healthy (no findings, at least one file read)
- `1` - needs attention (MEDIUM findings only, or INFO under `--strict`,
  or no files read)
- `2` - unhealthy (any HIGH finding) or unreadable input or an unknown flag

## Honest scope

**What this tool does:**
- Validates identifier **format** against the public spec of DOI, arXiv,
  ORCID, ISBN.
- Validates **checksums** where one is defined (ORCID Mod 11,2; ISBN-10
  mod-11; ISBN-13 mod-10).
- Checks BibTeX entries for structural defects (required fields,
  duplicate keys, empty values, unbalanced braces, future year).

**What this tool does NOT do:**
- It does not contact Crossref, DataCite, Semantic Scholar, OpenAlex,
  arXiv, or any other registry. A well-formed DOI may still fail to
  resolve.
- It does not detect hallucinated references by cross-checking against a
  database. For that, pair this tool with an online checker.
- It does not parse LaTeX macros or evaluate BibTeX string substitutions.
- It is not a full BibTeX parser - the parser is intentionally forgiving.
  Unparseable entries are skipped silently.

**Known false-positive modes:**
- DOI-003 fires on legitimate DOIs that contain percent-encoded whitespace.
- DOI-005 fires on arXiv IDs with a wrong `--current-year` setting.
- DOI-015 fires on BibTeX `eprint` fields that are not actually arXiv IDs
  but inherit `archiveprefix` from a previous entry. Pass `--disable
  DOI-015` or set `archiveprefix` on each entry.

A clean run is **origin-valid, not verified-safe**.

## Clean-room

Checksums and formats are derived from the public DOI Handbook, the public
arXiv identifier scheme, the public ORCID identifier spec (ISO 7064 Mod
11,2), the public ISO 2108 (ISBN) standard summary, and the public BibTeX
user's guide. **No reference implementation of any DOI, arXiv, ORCID, ISBN,
or BibTeX validator was read, vendored, or mirrored.** This is an
independent implementation and is not affiliated with or endorsed by the
authors of any such tool.

## License

MIT. See [LICENSE](LICENSE).

---

*Produced by Epimystic, a human-machine hybrid intelligence, under
maker-checker.*
