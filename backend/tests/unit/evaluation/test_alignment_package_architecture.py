"""Static architecture contract for the evaluator-alignment package."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).parents[3]
ALIGNMENT_ROOT = BACKEND_ROOT / "evaluation" / "experiments" / "alignment"
ALIGNMENT_PREFIX = "evaluation.experiments.alignment"

TARGET_PACKAGES = {
    "reference",
    "calibration",
    "evidence",
    "integrations",
    "integrations/langsmith",
    "reporting",
    "workflows",
}
ROOT_MODULES = {
    "__init__.py",
    "__main__.py",
    "cli_parser.py",
    "contracts.py",
    "paths.py",
    "self_test.py",
}
RETIRED_FLAT_MODULES = {
    "case_fixtures.py",
    "cases.py",
    "feedback.py",
    "feedback_models.py",
    "feedback_provenance.py",
    "label_set.py",
    "label_set_payload.py",
    "labeling.py",
    "labels.py",
    "live.py",
    "live_labeling.py",
    "live_support.py",
    "metadata.py",
    "phase_manifest.py",
    "policy.py",
    "primary_freeze.py",
    "publication.py",
    "publication_queues.py",
    "report.py",
    "report_tables.py",
    "report_validation.py",
    "result_metrics.py",
    "result_models.py",
    "results.py",
    "runner.py",
    "trace_models.py",
    "trace_queries.py",
    "tracing.py",
}
PURE_PACKAGES = ("reference", "calibration", "evidence")
FORBIDDEN_PURE_IMPORTS = (
    "langsmith",
    "app.platform.config",
    "app.platform.llm",
    "evaluation.judges",
    f"{ALIGNMENT_PREFIX}.integrations",
    f"{ALIGNMENT_PREFIX}.reporting",
    f"{ALIGNMENT_PREFIX}.workflows",
)
FORBIDDEN_WORKFLOW_IMPORTS = (
    "app.platform.config",
    f"{ALIGNMENT_PREFIX}.integrations.langsmith.client",
    "evaluation.judges.jev",
    "evaluation.judges.openai",
)


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _module_name(path: Path) -> str:
    relative = path.relative_to(BACKEND_ROOT).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    current_module = _module_name(path)
    package_parts = current_module.split(".")
    if path.name != "__init__.py":
        package_parts = package_parts[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    found.add(node.module)
                continue
            parent_count = node.level - 1
            base = package_parts[: len(package_parts) - parent_count]
            imported = tuple(node.module.split(".")) if node.module else ()
            found.add(".".join((*base, *imported)))
    return found


def _filesystem_writes(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    writes: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "write_bytes",
            "write_text",
        }:
            writes.append(node.lineno)
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "open":
            continue
        mode_node = node.args[1] if len(node.args) > 1 else None
        for keyword in node.keywords:
            if keyword.arg == "mode":
                mode_node = keyword.value
        if (
            isinstance(mode_node, ast.Constant)
            and isinstance(mode_node.value, str)
            and any(flag in mode_node.value for flag in "wax+")
        ):
            writes.append(node.lineno)
    return writes


def test_alignment_uses_approved_nested_package_shape() -> None:
    missing_packages = sorted(
        package
        for package in TARGET_PACKAGES
        if not (ALIGNMENT_ROOT / package / "__init__.py").is_file()
    )
    root_modules = {path.name for path in ALIGNMENT_ROOT.glob("*.py")}

    assert missing_packages == []
    assert root_modules == ROOT_MODULES


def test_alignment_flat_modules_are_retired_after_staged_migration() -> None:
    remaining = sorted(
        module for module in RETIRED_FLAT_MODULES if (ALIGNMENT_ROOT / module).exists()
    )

    assert remaining == []


def test_pure_alignment_packages_do_not_import_runtime_or_io_layers() -> None:
    violations: dict[str, list[str]] = {}
    for package in PURE_PACKAGES:
        for path in _python_files(ALIGNMENT_ROOT / package):
            blocked = sorted(
                imported
                for imported in _imports(path)
                if imported.startswith(FORBIDDEN_PURE_IMPORTS)
            )
            if blocked:
                violations[str(path.relative_to(BACKEND_ROOT))] = blocked

    assert violations == {}


def test_pure_alignment_packages_do_not_write_reports() -> None:
    violations = {
        str(path.relative_to(BACKEND_ROOT)): lines
        for package in PURE_PACKAGES
        for path in _python_files(ALIGNMENT_ROOT / package)
        if (lines := _filesystem_writes(path))
    }

    assert violations == {}


def test_alignment_workflows_receive_runtime_dependencies_from_the_cli() -> None:
    violations: dict[str, list[str]] = {}
    for path in _python_files(ALIGNMENT_ROOT / "workflows"):
        blocked = sorted(
            imported
            for imported in _imports(path)
            if imported.startswith(FORBIDDEN_WORKFLOW_IMPORTS)
        )
        if blocked:
            violations[str(path.relative_to(BACKEND_ROOT))] = blocked

    assert violations == {}


def test_alignment_internal_import_graph_is_acyclic() -> None:
    files = _python_files(ALIGNMENT_ROOT)
    modules = {_module_name(path) for path in files}
    graph = {
        _module_name(path): {imported for imported in _imports(path) if imported in modules}
        for path in files
    }
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            cycle = " -> ".join((*visiting[visiting.index(module) :], module))
            raise AssertionError(f"alignment import cycle: {cycle}")
        if module in visited:
            return
        visiting.append(module)
        for dependency in sorted(graph[module]):
            visit(dependency)
        visiting.pop()
        visited.add(module)

    for module in sorted(graph):
        visit(module)
