#!/usr/bin/env python3
"""Run the Sourcebridge C pack's one verified engine-test fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


PACK_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PACK_ROOT / "engine-tests" / "fixtures"
CASE = "tests/single-exec/00002.c"
EXPECTED_CASE = f"{CASE}.expected"
EXPECTED_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
VARIANT_PATH = PACK_ROOT / "variants" / "clang-22.1.8-x86_64-linux-c11.json"
FACT_PATH = PACK_ROOT / "evidence" / "00002.clang.facts.json"
sys.path.insert(0, str(PACK_ROOT))
from tools.extract_c_test_fact import extract_fact  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_source_validation(compiler: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            str(PACK_ROOT / "tools" / "validate_c_testsuite_case.py"),
            "--corpus-root",
            str(FIXTURE_ROOT),
            "--case",
            CASE,
            "--compiler",
            compiler,
        ],
        cwd=PACK_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    if len(sys.argv) != 2:
        raise ValueError("expected the catalogue fixture path")
    fixture = Path(sys.argv[1]).resolve()
    expected_fixture = (FIXTURE_ROOT / CASE).resolve()
    if fixture != expected_fixture:
        raise ValueError(f"unsupported fixture: {fixture}")
    expected_path = FIXTURE_ROOT / EXPECTED_CASE
    if digest(expected_path) != EXPECTED_DIGEST:
        raise ValueError("fixture expected-output digest differs from the pinned corpus manifest")

    variant = json.loads(VARIANT_PATH.read_text(encoding="utf-8"))
    source_result = run_source_validation(variant["compiler"]["command"])
    compiler_version = source_result["compiler"]
    expected_version = variant["compiler"]["version"]
    if expected_version not in compiler_version:
        raise ValueError(
            f"compiler evidence mismatch: expected {expected_version}, observed {compiler_version}"
        )

    extracted = extract_fact(fixture, FIXTURE_ROOT, variant)
    recorded = json.loads(FACT_PATH.read_text(encoding="utf-8"))
    if extracted != recorded:
        raise ValueError("compiler facts differ from checked-in C fact evidence")

    envelope = {
        "schema_version": 1,
        "source": {
            "status": "passed",
            "compiler": compiler_version,
            "standard": variant["standard"],
            "optimization": variant["optimization"],
            "fixture": CASE,
        },
        "extraction": {
            "status": "passed",
            "fact_schema": extracted["fact_schema"],
            "evidence": "evidence/00002.clang.facts.json",
            "evidence_sha256": digest(FACT_PATH),
            "source_sha256": extracted["source"]["sha256"],
        },
        "target": {
            "status": "blocked",
            "reason": "this prototype has no generic C target backend or C-to-Rust adapter",
        },
        "oracle": {
            "status": "passed",
            "kind": "c-testsuite-single-exec",
            "expected": EXPECTED_CASE,
            "expected_sha256": EXPECTED_DIGEST,
            "comparison": "exit-code-and-combined-stdout-stderr",
        },
    }
    print(json.dumps(envelope, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
