#!/usr/bin/env python3
"""Extract constrained compiler facts from one upstream C test case."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


def descendants(node: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for child in node.get("inner", []):
        result.append(child)
        result.extend(descendants(child))
    return result


def expression(node: dict[str, Any]) -> dict[str, Any]:
    kind = node.get("kind")
    if kind == "IntegerLiteral":
        return {
            "kind": "integer_literal",
            "type": node["type"]["qualType"],
            "value": int(node["value"]),
        }
    if kind == "BinaryOperator" and node.get("opcode") in {"+", "-", "*", "/"}:
        operands = node.get("inner", [])
        if len(operands) != 2:
            raise ValueError("binary expression must have exactly two operands")
        return {
            "kind": "binary_operator",
            "operator": node["opcode"],
            "type": node["type"]["qualType"],
            "left": expression(operands[0]),
            "right": expression(operands[1]),
        }
    raise ValueError(f"unsupported return expression: {kind}")


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--variant", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.corpus_root.resolve()
    source = (root / args.source).resolve()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError("--source must stay inside --corpus-root") from error
    if not source.is_file():
        raise ValueError(f"source does not exist: {args.source}")
    variant = json.loads(args.variant.read_text(encoding="utf-8"))
    if variant.get("language") != "c":
        raise ValueError("variant language must be c")
    compiler = variant["compiler"]["command"]
    standard = variant["standard"]
    result = subprocess.run(
        [compiler, f"--std={standard}", "-fsyntax-only", "-Xclang", "-ast-dump=json", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    ast = json.loads(result.stdout)
    functions = []
    for node in descendants(ast):
        if node.get("kind") != "FunctionDecl" or node.get("name") != "main":
            continue
        compound = next((item for item in node.get("inner", []) if item.get("kind") == "CompoundStmt"), None)
        if compound is None:
            raise ValueError("main has no compound body")
        returns = [item for item in descendants(compound) if item.get("kind") == "ReturnStmt"]
        if len(returns) != 1 or len(returns[0].get("inner", [])) != 1:
            raise ValueError("main must have exactly one return expression")
        functions.append({
            "name": "main",
            "return_type": node["type"]["qualType"].split(" (")[0],
            "return_expression": expression(returns[0]["inner"][0]),
        })
    if len(functions) != 1:
        raise ValueError("source must define exactly one supported main function")
    payload = {
        "schema_version": 1,
        "fact_schema": "sourcebridge.c.ast-facts.v1",
        "source": {
            "path": relative.as_posix(),
            "sha256": source_sha256(source),
        },
        "variant": variant,
        "functions": functions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"extracted facts for {relative.as_posix()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
