#!/usr/bin/env python3
"""Validate the bounded native C-to-Rust path against one upstream case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CASE = "tests/single-exec/00002.c"


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        raise ValueError(f"command failed with exit status {result.returncode}: {' '.join(command)}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--rust-pack", type=Path, required=True)
    args = parser.parse_args()
    corpus_root = args.corpus_root.resolve()
    rust_pack = args.rust_pack.resolve()
    source = corpus_root / CASE
    expected = source.with_suffix(".c.expected")
    if not source.is_file() or not expected.is_file():
        parser.error(f"missing pinned upstream case or expected output: {CASE}")
    if not (rust_pack / "Cargo.toml").is_file():
        parser.error("--rust-pack must contain Cargo.toml")

    with tempfile.TemporaryDirectory(prefix="sourcebridge-c-rust-") as temporary:
        temporary_path = Path(temporary)
        facts = temporary_path / "facts.json"
        generated = temporary_path / "case.rs"
        executable = temporary_path / "case"
        run([
            sys.executable,
            str(ROOT / "tools" / "validate_c_testsuite_case.py"),
            "--corpus-root",
            str(corpus_root),
            "--case",
            CASE,
        ])
        run([
            sys.executable,
            str(ROOT / "tools" / "extract_c_test_fact.py"),
            "--corpus-root",
            str(corpus_root),
            "--source",
            CASE,
            "--variant",
            str(ROOT / "variants" / "clang-22.1.8-x86_64-linux-c11.json"),
            "--output",
            str(facts),
        ])
        emitted = run([
            "cargo",
            "run",
            "--quiet",
            "--bin",
            "sourcebridge-rust-emit",
            "--",
            str(facts),
        ], cwd=rust_pack)
        generated.write_text(emitted.stdout, encoding="utf-8")
        run(["rustc", "-Dwarnings", str(generated), "-o", str(executable)])
        target = subprocess.run([str(executable)], capture_output=True)
        actual = target.stdout + target.stderr
        if target.returncode:
            raise ValueError(f"generated Rust exited with {target.returncode}")
        if actual != expected.read_bytes():
            raise ValueError("generated Rust output differs from upstream expected output")
    print(json.dumps({
        "case": CASE,
        "source_status": "passed",
        "target_status": "passed",
        "oracle": "stdout-stderr-and-exit-code",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
