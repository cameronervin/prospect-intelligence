"""GitHub source archives remain runnable without Git metadata."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMMON = ROOT / "scripts/common.sh"
SNAPSHOT = ROOT / "scripts/copy-reviewable-snapshot.py"
SECRET_SCAN = ROOT / "scripts/secret-scan.sh"
TEST_E2E = ROOT / "scripts/test-e2e.sh"


def _run(*command: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _source_id(root: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(
        "python3",
        str(SNAPSHOT),
        "--source-id",
        str(root),
        cwd=root,
        check=check,
    )


def _archive_fixture(root: Path) -> None:
    _write(
        root / ".gitignore",
        ".env\nnode_modules/\n.next/\n__pycache__/\nartifacts/\n",
    )
    _write(root / ".env", "OPENAI_API_KEY=not-reviewable\n")
    _write(root / ".env.example", "OPENAI_API_KEY=\n")
    _write(root / ".codex/config.toml", "project = 'archive'\n")
    _write(root / "backend/app.py", "VALUE = 1\n")
    _write(root / "frontend/node_modules/package/index.js", "generated\n")
    _write(root / "frontend/.next/build.txt", "generated\n")
    _write(root / "backend/__pycache__/app.pyc", "generated\n")
    _write(root / "artifacts/result.json", "generated\n")


def _init_git_repository(root: Path) -> None:
    _run("git", "init", "--quiet", cwd=root)
    _run("git", "config", "user.name", "Archive Test", cwd=root)
    _run("git", "config", "user.email", "archive@example.test", cwd=root)


def _expected_git_source_id(root: Path) -> str:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--binary", "HEAD", "--", "."],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.splitlines()
    fingerprint = bytearray(head)
    fingerprint.extend(diff)
    for relative in sorted(untracked):
        blob = subprocess.run(
            ["git", "hash-object", "--", os.fsdecode(relative)],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        fingerprint.extend(relative)
        fingerprint.extend(b" ")
        fingerprint.extend(blob)
    return (
        subprocess.run(
            ["git", "hash-object", "--stdin"],
            cwd=root,
            check=True,
            input=bytes(fingerprint),
            capture_output=True,
        )
        .stdout.decode()
        .strip()
    )


def test_repo_root_uses_renamed_script_location_without_git(tmp_path: Path) -> None:
    archive = tmp_path / "renamed takehome submission"
    scripts = archive / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(COMMON, scripts / "common.sh")
    _write(
        scripts / "probe.sh",
        '#!/usr/bin/env sh\nset -eu\n. "$(dirname -- "$0")/common.sh"\nrepo_root\n',
    )

    completed = _run("sh", str(scripts / "probe.sh"), cwd=tmp_path)

    assert Path(completed.stdout.strip()) == archive


def test_archive_snapshot_honors_ignore_rules_inside_parent_git_repo(tmp_path: Path) -> None:
    _init_git_repository(tmp_path)
    _write(tmp_path / "parent.txt", "unrelated parent\n")
    _run("git", "add", "parent.txt", cwd=tmp_path)
    _run("git", "commit", "--quiet", "-m", "parent", cwd=tmp_path)
    archive = tmp_path / "renamed archive"
    _archive_fixture(archive)
    destination = tmp_path / "snapshot"

    _run("python3", str(SNAPSHOT), str(archive), str(destination), cwd=archive)

    assert (destination / ".gitignore").is_file()
    assert (destination / ".env.example").is_file()
    assert (destination / ".codex/config.toml").is_file()
    assert (destination / "backend/app.py").is_file()
    assert not (destination / ".env").exists()
    assert not (destination / "frontend/node_modules").exists()
    assert not (destination / "frontend/.next").exists()
    assert not (destination / "backend/__pycache__").exists()
    assert not (destination / "artifacts").exists()
    assert not (destination / "parent.txt").exists()


def test_archive_source_id_is_root_independent_and_reviewable_content_sensitive(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first name"
    second = tmp_path / "second name"
    _archive_fixture(first)
    shutil.copytree(first, second)

    baseline = _source_id(first).stdout.strip()
    assert baseline.startswith("archive-sha256-")
    assert _source_id(second).stdout.strip() == baseline

    _write(second / ".env", "OPENAI_API_KEY=changed-but-ignored\n")
    assert _source_id(second).stdout.strip() == baseline

    _write(second / "backend/app.py", "VALUE = 2\n")
    changed_content = _source_id(second).stdout.strip()
    assert changed_content != baseline

    (second / "backend/app.py").rename(second / "backend/renamed.py")
    assert _source_id(second).stdout.strip() != changed_content


def test_git_source_id_preserves_clean_and_dirty_fingerprints(tmp_path: Path) -> None:
    _init_git_repository(tmp_path)
    _write(tmp_path / ".gitignore", ".env\n")
    _write(tmp_path / "tracked.txt", "tracked\n")
    _run("git", "add", ".", cwd=tmp_path)
    _run("git", "commit", "--quiet", "-m", "initial", cwd=tmp_path)

    assert _source_id(tmp_path).stdout.strip() == _expected_git_source_id(tmp_path)

    _write(tmp_path / "tracked.txt", "dirty\n")
    _write(tmp_path / "untracked.txt", "untracked\n")
    _write(tmp_path / ".env", "ignored\n")
    assert _source_id(tmp_path).stdout.strip() == _expected_git_source_id(tmp_path)


def test_snapshot_rejects_tracked_symlink_outside_root(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _init_git_repository(repository)
    outside = tmp_path / "outside.txt"
    _write(outside, "outside\n")
    (repository / "escape.txt").symlink_to(outside)
    _run("git", "add", "escape.txt", cwd=repository)
    _run("git", "commit", "--quiet", "-m", "symlink", cwd=repository)

    completed = _source_id(repository, check=False)

    assert completed.returncode != 0
    assert "outside the repository root" in completed.stderr


def test_secret_scan_runs_from_archive_without_git(tmp_path: Path) -> None:
    archive = tmp_path / "emailed submission"
    scripts = archive / "scripts"
    scripts.mkdir(parents=True)
    for source in (COMMON, SNAPSHOT, SECRET_SCAN):
        shutil.copy2(source, scripts / source.name)
    _write(archive / ".gitignore", ".env\n")
    _write(archive / ".env.example", "OPENAI_API_KEY=\n")
    _write(archive / "README.md", "safe archive\n")

    completed = _run("sh", str(scripts / "secret-scan.sh"), cwd=archive)

    assert completed.stdout.strip() == "secret scan passed"


def test_e2e_selection_generates_archive_source_id_without_git(tmp_path: Path) -> None:
    archive = tmp_path / "renamed e2e archive"
    scripts = archive / "scripts"
    scripts.mkdir(parents=True)
    for source in (COMMON, SNAPSHOT, TEST_E2E):
        shutil.copy2(source, scripts / source.name)
    _write(archive / ".gitignore", ".env\n")
    _write(archive / "deploy/envs/.env.local.example", "SAFE=true\n")
    _write(archive / "deploy/compose/compose.yml", "services: {}\n")
    _write(archive / "deploy/compose/compose.e2e.yml", "services: {}\n")
    docker = tmp_path / "docker"
    _write(
        docker,
        """#!/bin/sh
set -eu
case "$*" in
  "compose version") exit 0 ;;
  *" config --quiet") exit 0 ;;
  *" ps --all --quiet"*) exit 0 ;;
  *) printf 'unexpected docker call: %s\\n' "$*" >&2; exit 9 ;;
esac
""",
    )
    docker.chmod(0o755)
    environment = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}

    completed = subprocess.run(
        ["sh", str(scripts / "test-e2e.sh"), "--stack-selection"],
        cwd=archive,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "isolated"
