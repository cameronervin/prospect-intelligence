from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_backend_docker_context_includes_runtime_scripts() -> None:
    rules = (ROOT / "deploy/docker/backend.Dockerfile.dockerignore").read_text().splitlines()

    assert "!backend/scripts/**" in rules
