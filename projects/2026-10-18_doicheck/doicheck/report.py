"""Text and JSON output formatting for doicheck."""

from __future__ import annotations

import json
from typing import TextIO

from .types import ScanResult, Severity


_SEVERITY_ORDER = (Severity.HIGH, Severity.MEDIUM, Severity.INFO)


def _visible(text: str) -> str:
    """Render ``text`` so every character is printable ASCII.

    Any character outside printable ASCII (0x20-0x7E) is rewritten as
    ``<U+XXXX>``. The report must never crash on a console that cannot
    encode what it is reporting (a Windows console on code page 1252
    cannot encode a Cyrillic letter or a zero-width space, and echoing
    one raw crashes the reporter mid-write), and a report that re-echoed
    hidden characters raw would reconceal them in the output meant to
    expose them.
    """
    out = []
    for ch in text or "":
        cp = ord(ch)
        if 32 <= cp < 127:
            out.append(ch)
        else:
            out.append("<U+%04X>" % cp)
    return "".join(out)


def write_text(result: ScanResult, stream: TextIO) -> None:
    if not result.findings:
        stream.write(
            "doicheck: " + result.verdict.value
            + "; files=" + str(result.files_scanned)
            + " identifiers=" + str(result.identifiers_scanned)
            + " findings=0\n"
        )
        return
    by_sev = {s: [f for f in result.findings if f.severity is s]
              for s in _SEVERITY_ORDER}
    for sev in _SEVERITY_ORDER:
        for f in by_sev[sev]:
            location = _visible(f.path)
            if f.line:
                location += ":" + str(f.line)
            subj = f.subject or "(no subject)"
            stream.write(
                sev.value + " " + f.rule_id + " " + location
                + " [" + _visible(subj) + "]: "
                + _visible(f.message) + "\n"
            )
            if f.hint:
                stream.write("    hint: " + _visible(f.hint) + "\n")
            if f.citation:
                stream.write("    cite: " + _visible(f.citation) + "\n")
    stream.write(
        "doicheck: " + result.verdict.value
        + "; files=" + str(result.files_scanned)
        + " identifiers=" + str(result.identifiers_scanned)
        + " findings=" + str(len(result.findings)) + "\n"
    )


def write_json(result: ScanResult, stream: TextIO) -> None:
    json.dump(result.to_dict(), stream, indent=2)
    stream.write("\n")


__all__ = ["write_text", "write_json"]
