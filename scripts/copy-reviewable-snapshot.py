"""Copy or fingerprint reviewable files from a checkout or source archive."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _completed(command: list[str], *, root: Path, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        command,
        cwd=root,
        check=True,
        input=input_bytes,
        capture_output=True,
    ).stdout


def _exact_git_checkout(root: Path) -> bool:
    try:
        top_level = _completed(["git", "rev-parse", "--show-toplevel"], root=root)
        _completed(["git", "rev-parse", "--verify", "HEAD^{commit}"], root=root)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return Path(os.fsdecode(top_level.strip())).resolve() == root


def _git_reviewable_paths(root: Path) -> list[Path]:
    output = _completed(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        root=root,
    )
    return [Path(os.fsdecode(value)) for value in output.split(b"\0") if value]


def _archive_reviewable_paths(root: Path) -> list[Path]:
    output = _completed(
        [
            "rg",
            "--files",
            "--hidden",
            "--no-require-git",
            "--null",
            "--glob",
            "!.git/**",
        ],
        root=root,
    )
    return [Path(os.fsdecode(value)) for value in output.split(b"\0") if value]


def reviewable_paths(root: Path) -> list[Path]:
    paths = _git_reviewable_paths(root) if _exact_git_checkout(root) else _archive_reviewable_paths(root)
    return sorted(set(paths), key=lambda path: os.fsencode(path.as_posix()))


def reviewable_files(root: Path) -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    for relative in reviewable_paths(root):
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"reviewable path escapes the repository root: {relative}")
        source = root / relative
        resolved = source.resolve()
        if root not in resolved.parents:
            raise ValueError(f"reviewable path resolves outside the repository root: {relative}")
        if not resolved.is_file():
            continue
        files.append((relative, resolved))
    return files


def _git_source_id(root: Path) -> str:
    fingerprint = bytearray(_completed(["git", "rev-parse", "HEAD"], root=root))
    fingerprint.extend(
        _completed(
            ["git", "diff", "--no-ext-diff", "--binary", "HEAD", "--", "."],
            root=root,
        )
    )
    untracked = _completed(
        ["git", "ls-files", "--others", "--exclude-standard"],
        root=root,
    ).splitlines()
    for encoded_path in sorted(untracked):
        fingerprint.extend(encoded_path)
        fingerprint.extend(b" ")
        fingerprint.extend(
            _completed(
                ["git", "hash-object", "--", os.fsdecode(encoded_path)],
                root=root,
            )
        )
    return os.fsdecode(
        _completed(["git", "hash-object", "--stdin"], root=root, input_bytes=fingerprint)
    ).strip()


def _archive_source_id(files: list[tuple[Path, Path]]) -> str:
    digest = hashlib.sha256()
    for relative, source in files:
        digest.update(os.fsencode(relative.as_posix()))
        digest.update(b"\0")
        with source.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return f"archive-sha256-{digest.hexdigest()}"


def source_id(root: Path) -> str:
    files = reviewable_files(root)
    if _exact_git_checkout(root):
        return _git_source_id(root)
    return _archive_source_id(files)


def copy_reviewable_snapshot(root: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for relative, source in reviewable_files(root):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--source-id":
        root = Path(sys.argv[2]).resolve()
        print(source_id(root))
        return 0
    if len(sys.argv) != 3:
        raise ValueError(
            "usage: copy-reviewable-snapshot.py ROOT DESTINATION\n"
            "       copy-reviewable-snapshot.py --source-id ROOT"
        )

    root = Path(sys.argv[1]).resolve()
    destination = Path(sys.argv[2]).resolve()
    copy_reviewable_snapshot(root, destination)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
