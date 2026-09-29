"""Copy Git-visible files to a temporary directory for secret scanning."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def reviewable_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [Path(value.decode()) for value in result.stdout.split(b"\0") if value]


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: copy-reviewable-snapshot.py ROOT DESTINATION")

    root = Path(sys.argv[1]).resolve()
    destination = Path(sys.argv[2]).resolve()
    destination.mkdir(parents=True, exist_ok=False)

    for relative in reviewable_paths(root):
        source = (root / relative).resolve()
        if root not in source.parents or not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

