"""Command-line entry for nbexport.

Invokable as ``python -m nbexport`` (via __main__.py). argparse owns
``--help`` and unknown-flag handling, which keeps the exit-code contract
in repro-lab/docs/CONVENTIONS.md intact.

Two usage shapes:

  - Default: scan one or more notebooks and report ordering defects.
  - ``--emit-script linear|executed``: additionally write a .py file
    with the cells in the chosen order.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence, TextIO

from . import __version__
from .export import emit_script
from .notebook import parse_notebook
from .report import write_json, write_text
from .scanner import scan_paths
from .types import Options
from .verdict import exit_code


def _parse_argv(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="nbexport",
        description=(
            "Lint Jupyter notebooks for execution-order defects, and"
            " optionally emit a .py script in linear or recorded"
            " execution order. Zero network, zero third-party"
            " dependencies."
        ),
    )
    p.add_argument(
        "--version", action="version",
        version="nbexport " + __version__,
    )
    p.add_argument(
        "paths", nargs="+",
        help="file(s) or director(y|ies) to scan",
    )
    p.add_argument(
        "--json", action="store_true",
        help="emit machine-readable JSON findings instead of text",
    )
    p.add_argument(
        "--strict", action="store_true",
        help="surface INFO rules and treat INFO-only outcomes as"
             " needs-attention",
    )
    p.add_argument(
        "--include-info", action="store_true",
        help="surface INFO rules in output (without upgrading verdict)",
    )
    p.add_argument(
        "--disable", action="append", default=[], metavar="RULE_ID",
        help="disable a rule (repeatable)",
    )
    p.add_argument(
        "--only", action="append", default=[], metavar="RULE_ID",
        help="run only the given rule (repeatable)",
    )
    p.add_argument(
        "--emit-script", choices=("linear", "executed"), default=None,
        help="additionally write a .py script in the given order."
             " 'linear' = file order; 'executed' = recorded"
             " execution_count order",
    )
    p.add_argument(
        "-o", "--output", default=None, metavar="PATH",
        help="output path for --emit-script (defaults to <input>.py)",
    )
    return p.parse_args(list(argv))


def main(
    argv: Optional[Sequence[str]] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    args = _parse_argv(argv if argv is not None else sys.argv[1:])
    options = Options(
        strict=args.strict,
        include_info=args.include_info,
        disabled=tuple(args.disable),
        only=tuple(args.only),
        emit_mode=args.emit_script or "none",
    )
    result = scan_paths(args.paths, options)
    if args.json:
        write_json(result, stdout)
    else:
        write_text(result, stdout)
    if args.emit_script is not None:
        # Emit per input file. Only works on explicit file paths, not
        # directories: a reader asked for a script per notebook, and
        # fanning out silently would be surprising.
        for path in args.paths:
            if not os.path.isfile(path):
                stderr.write("nbexport: --emit-script requires a file"
                             " path, not a directory: " + path + "\n")
                continue
            try:
                with open(path, "r", encoding="utf-8",
                          errors="replace") as f:
                    content = f.read()
            except OSError as e:
                stderr.write("nbexport: cannot read " + path + ": "
                             + str(e) + "\n")
                continue
            nb = parse_notebook(content)
            if nb.parse_error:
                stderr.write("nbexport: cannot parse " + path + ": "
                             + nb.parse_error + "\n")
                continue
            out_path = args.output
            if out_path is None:
                base, _ = os.path.splitext(path)
                out_path = base + ".py"
            try:
                with open(out_path, "w", encoding="utf-8",
                          newline="\n") as f:
                    f.write(emit_script(nb, args.emit_script))
            except OSError as e:
                stderr.write("nbexport: cannot write " + out_path + ": "
                             + str(e) + "\n")
    return exit_code(result.verdict, options)


__all__ = ["main"]
