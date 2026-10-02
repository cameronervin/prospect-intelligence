"""Delivery configuration and local E2E selection stay safe by construction."""

import json
import os
import subprocess
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "deploy/compose/compose.yml"
DEV_COMPOSE = ROOT / "deploy/compose/compose.dev.yml"
E2E_COMPOSE = ROOT / "deploy/compose/compose.e2e.yml"
FRONTEND_DOCKERFILE = ROOT / "deploy/docker/frontend.Dockerfile"
ENV_FILE = ROOT / "deploy/envs/.env.local.example"


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _sequence(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _strings(value: object) -> list[str]:
    items = _sequence(value)
    assert all(isinstance(item, str) for item in items)
    return cast("list[str]", items)


def _compose_config(
    *files: Path,
    environment: dict[str, str] | None = None,
) -> dict[str, object]:
    command = ["docker", "compose", "--env-file", str(ENV_FILE)]
    for file in files:
        command.extend(("--file", str(file)))
    command.extend(("config", "--format", "json"))
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(environment or {})},
    )
    value: object = json.loads(completed.stdout)
    return _mapping(value)


def test_development_override_preserves_runtime_security_boundaries() -> None:
    config = _compose_config(
        COMPOSE,
        DEV_COMPOSE,
        environment={"TAKEHOME_DEMO_AUTH_ENABLED": "false"},
    )
    assert config["name"] == "langchain-takehome"
    services = _mapping(config["services"])
    backend = _mapping(services["backend"])
    frontend = _mapping(services["frontend"])
    backend_command = _strings(backend["command"])
    backend_environment = _mapping(backend["environment"])
    backend_volumes = [_mapping(item) for item in _sequence(backend["volumes"])]
    frontend_command = _strings(frontend["command"])
    frontend_volumes = [_mapping(item) for item in _sequence(frontend["volumes"])]

    assert backend["user"] == "10001:10001"
    assert backend["read_only"] is True
    assert "--reload" in backend_command
    assert "--workers" not in backend_command
    assert backend_environment["TAKEHOME_DEMO_AUTH_ENABLED"] == "true"
    assert len(backend_volumes) == 1
    assert all(volume["read_only"] is True for volume in backend_volumes)
    assert "healthcheck" in backend

    assert frontend["user"] == "10001:10001"
    assert frontend["read_only"] is True
    assert _mapping(frontend["build"])["target"] == "development"
    assert frontend_command[:3] == ["npm", "run", "dev"]
    assert "healthcheck" in frontend
    assert all(volume["read_only"] is True for volume in frontend_volumes)
    assert all(
        not cast(str, volume["source"]).endswith("/next-env.d.ts") for volume in frontend_volumes
    )
    forbidden = ("node_modules", ".next", "test-results", "deploy/envs")
    assert all(
        not any(marker in cast(str, volume["source"]) for marker in forbidden)
        for volume in frontend_volumes
    )
    assert any(item.startswith("/app/.next:") for item in _strings(frontend["tmpfs"]))
    dockerfile = FRONTEND_DOCKERFILE.read_text()
    assert "ln -s .next/next-env.d.ts /app/next-env.d.ts" in dockerfile


def test_production_compose_remains_immutable() -> None:
    config = _compose_config(COMPOSE)
    services = _mapping(config["services"])
    for name in ("backend", "frontend"):
        service = _mapping(services[name])
        assert service["user"] == "10001:10001"
        assert service["read_only"] is True
        assert "volumes" not in service


def test_e2e_override_declares_reuse_safety_and_source_identity() -> None:
    config = _compose_config(COMPOSE, E2E_COMPOSE)
    dev_config = _compose_config(COMPOSE, DEV_COMPOSE, E2E_COMPOSE)
    selection = (ROOT / "scripts/test-e2e.sh").read_text()
    services = _mapping(config["services"])
    backend = _mapping(services["backend"])
    frontend = _mapping(services["frontend"])
    dev_backend = _mapping(_mapping(dev_config["services"])["backend"])

    for service in (backend, frontend):
        labels = _mapping(service["labels"])
        assert labels["com.langchain-takehome.e2e-safe"] == "true"
        assert labels["com.langchain-takehome.e2e-source-id"] == "unset"
    environment = _mapping(backend["environment"])
    assert environment["TAKEHOME_ENVIRONMENT"] == "test"
    assert environment["TAKEHOME_EXTERNAL_LIVE_ENABLED"] == "false"
    assert environment["LANGSMITH_TRACING"] == "false"
    assert environment["OPENAI_API_KEY"] == ""
    assert _strings(dev_backend["command"])[1] == "tests.e2e_app:create_e2e_app"
    assert "--stack-selection" in selection


def _selection(tmp_path: Path, mode: str, *, ci: bool = False) -> subprocess.CompletedProcess[str]:
    docker = tmp_path / "docker"
    docker.write_text(
        """#!/bin/sh
set -eu
case "$*" in
  "compose version") exit 0 ;;
  *" config --quiet") exit 0 ;;
  *" ps --all --quiet"*)
    [ "${FAKE_STACK_MODE}" = "absent" ] && exit 0
    last=""
    for argument in "$@"; do last=$argument; done
    case "$last" in
      postgres|backend|frontend) printf '%s-container\\n' "$last" ;;
      *) printf '%s\\n' postgres-container backend-container frontend-container ;;
    esac
    ;;
  *"State.Health.Status"*)
    [ "${FAKE_STACK_MODE}" = "unhealthy" ] && printf '%s\\n' starting || printf '%s\\n' healthy
    ;;
  *"e2e-safe"*)
    case "${FAKE_STACK_MODE}" in
      safe) printf 'true|%s\\n' "${TAKEHOME_E2E_SOURCE_ID}" ;;
      stale) printf '%s\\n' 'true|stale-source' ;;
      *) printf '%s\\n' '|' ;;
    esac
    ;;
  *) printf 'unexpected docker call: %s\\n' "$*" >&2; exit 9 ;;
esac
"""
    )
    docker.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_STACK_MODE": mode,
        "TAKEHOME_E2E_SOURCE_ID": "current-source",
    }
    if ci:
        environment["CI"] = "true"
    else:
        environment.pop("CI", None)
    return subprocess.run(
        ["sh", str(ROOT / "scripts/test-e2e.sh"), "--stack-selection"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("mode", ["unsafe", "stale", "unhealthy"])
def test_present_standard_stack_must_be_safe_and_current(tmp_path: Path, mode: str) -> None:
    completed = _selection(tmp_path, mode)

    assert completed.returncode == 1
    assert "refusing a parallel E2E project" in completed.stderr


def test_safe_current_standard_stack_is_reused(tmp_path: Path) -> None:
    completed = _selection(tmp_path, "safe")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "reuse"


def test_absent_standard_stack_selects_isolated_project(tmp_path: Path) -> None:
    completed = _selection(tmp_path, "absent")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "isolated"


def test_ci_refuses_parallel_project_when_standard_stack_exists(tmp_path: Path) -> None:
    completed = _selection(tmp_path, "safe", ci=True)

    assert completed.returncode == 1
    assert "refusing to start a parallel CI E2E project" in completed.stderr


def test_ci_without_standard_stack_selects_isolated_project(tmp_path: Path) -> None:
    completed = _selection(tmp_path, "absent", ci=True)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "isolated"
