#!/usr/bin/env python3
"""Create a detached checkout of the pinned upstream C test corpus."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


REMOTE = "https://github.com/c-testsuite/c-testsuite.git"
REVISION = "5c7275656d751de0e68b2d340a95b5681858ed07"


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        if any(destination.iterdir()):
            parser.error("--destination must not exist or must be empty")
        destination.rmdir()
    run("git", "clone", REMOTE, str(destination))
    run("git", "-C", str(destination), "checkout", "--detach", REVISION)
    observed = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if observed != REVISION:
        raise ValueError(f"checked out {observed}, expected {REVISION}")
    print(f"bootstrapped {REMOTE}@{REVISION}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)

