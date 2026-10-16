#!/usr/bin/env python3
"""Reject accidental direct imports from the Linux-specific conversion pack."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "migration" / "linux-rs-candidate-inventory.json"
DISPOSITIONS = {"adapt", "already_represented", "retain"}


def main() -> int:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if inventory.get("schema_version") != 1:
        raise ValueError("unsupported inventory schema")
    source = inventory.get("source", {})
    if source.get("remote") != "https://github.com/awto-au/linux-rs.git":
        raise ValueError("unexpected migration source remote")
    if len(source.get("revision", "")) != 40:
        raise ValueError("migration source revision must be a full commit identifier")
    seen_paths = set()
    adapted = 0
    for candidate in inventory.get("candidates", []):
        source_path = candidate.get("source_path", "")
        path = Path(source_path)
        if not source_path or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"invalid source path: {source_path!r}")
        if source_path in seen_paths:
            raise ValueError(f"duplicate source path: {source_path}")
        seen_paths.add(source_path)
        disposition = candidate.get("disposition")
        if disposition not in DISPOSITIONS:
            raise ValueError(f"invalid disposition for {source_path}: {disposition!r}")
        if not candidate.get("reason"):
            raise ValueError(f"missing reason for {source_path}")
        if disposition == "adapt":
            if not candidate.get("next_validation"):
                raise ValueError(f"adapt candidate lacks validation: {source_path}")
            adapted += 1
    if adapted != 1:
        raise ValueError(f"expected one controlled adaptation candidate, found {adapted}")
    print(f"verified {len(seen_paths)} Linux-rs migration candidates")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
