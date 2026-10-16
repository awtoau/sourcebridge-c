#!/usr/bin/env python3
"""Record a deterministic whole-tree manifest for the pinned C test corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


REMOTE = "https://github.com/c-testsuite/c-testsuite.git"
REVISION = "5c7275656d751de0e68b2d340a95b5681858ed07"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.corpus_root.resolve()
    observed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if observed != REVISION:
        parser.error(f"corpus revision is {observed}, expected {REVISION}")
    files = []
    tree = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and ".git" not in item.parts):
        relative = path.relative_to(root).as_posix()
        digest = sha256(path)
        files.append({"path": relative, "sha256": digest})
        tree.update(relative.encode())
        tree.update(b"\0")
        tree.update(digest.encode())
        tree.update(b"\0")
    payload = {
        "schema_version": 1,
        "corpus": {
            "remote": REMOTE,
            "revision": REVISION,
            "tree_sha256": tree.hexdigest(),
        },
        "files": files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"recorded {len(files)} corpus files")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)

