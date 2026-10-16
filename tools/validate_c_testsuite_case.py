#!/usr/bin/env python3
"""Compile and execute one upstream c-testsuite single-exec case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def corpus_file(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("--case must stay inside --corpus-root") from error
    if not candidate.is_file():
        raise ValueError(f"case does not exist: {relative}")
    if candidate.suffix != ".c":
        raise ValueError("--case must name a .c source file")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--compiler", default="clang")
    args = parser.parse_args()
    root = args.corpus_root.resolve()
    source = corpus_file(root, args.case)
    expected = source.with_suffix(".c.expected")
    if not expected.is_file():
        parser.error(f"expected-output file is missing: {expected.name}")
    with tempfile.TemporaryDirectory(prefix="sourcebridge-c-") as temporary:
        executable = Path(temporary) / "case"
        compile_result = subprocess.run(
            [args.compiler, "--std=c11", "-O0", str(source), "-o", str(executable)],
            capture_output=True,
            text=True,
        )
        if compile_result.returncode:
            print(compile_result.stderr, file=sys.stderr, end="")
            return compile_result.returncode
        run_result = subprocess.run([str(executable)], capture_output=True)
    actual = run_result.stdout + run_result.stderr
    expected_bytes = expected.read_bytes()
    if run_result.returncode:
        print(f"case exited with {run_result.returncode}", file=sys.stderr)
        return run_result.returncode
    if actual != expected_bytes:
        print("case output differs from upstream expected output", file=sys.stderr)
        return 1
    compiler_version = subprocess.run(
        [args.compiler, "--version"], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0]
    print(json.dumps({
        "case": source.relative_to(root).as_posix(),
        "compiler": compiler_version,
        "status": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)

