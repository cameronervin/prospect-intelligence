"""Maintain reviewable evaluation package boundaries."""

import ast
from pathlib import Path

MAX_MODULE_LINES = 250
BACKEND_ROOT = Path(__file__).parents[3]
EVALUATION_ROOT = BACKEND_ROOT / "evaluation"

EXPECTED_CONTRACT_MODULES = {"__init__.py", "observations.py", "snapshot.py"}
EXPECTED_EVALUATOR_MODULES = {
    "__init__.py",
    "analysis_correctness.py",
    "cost.py",
    "file_contract.py",
    "injection_resistance.py",
    "lane_precision.py",
    "latency.py",
    "numeric_grounding.py",
    "suite.py",
    "tool_call_count.py",
    "trajectory.py",
    "verdict_accuracy.py",
}
EXPECTED_JUDGE_MODULES = {"__init__.py", "jev.py"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_evaluation_modules_stay_within_reviewable_size() -> None:
    roots = (BACKEND_ROOT / "evaluation", BACKEND_ROOT / "tests" / "unit" / "evaluation")
    oversized = {
        str(path.relative_to(BACKEND_ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for root in roots
        for path in root.rglob("*.py")
        if len(path.read_text(encoding="utf-8").splitlines()) > MAX_MODULE_LINES
    }

    assert oversized == {}


def test_populated_evaluation_packages_have_no_gitkeep_placeholders() -> None:
    assert list((BACKEND_ROOT / "evaluation").rglob(".gitkeep")) == []


def test_evaluation_packages_have_single_purpose_module_shape() -> None:
    assert {path.name for path in (EVALUATION_ROOT / "contracts").glob("*.py")} == (
        EXPECTED_CONTRACT_MODULES
    )
    assert {path.name for path in (EVALUATION_ROOT / "evaluators").glob("*.py")} == (
        EXPECTED_EVALUATOR_MODULES
    )
    assert {path.name for path in (EVALUATION_ROOT / "judges").glob("*.py")} == (
        EXPECTED_JUDGE_MODULES
    )


def test_evaluation_dependency_directions_are_enforced() -> None:
    forbidden_by_area = {
        "contracts": (
            "evaluation.evaluators",
            "evaluation.experiments",
            "evaluation.judges",
            "evaluation.targets",
        ),
        "evaluators": ("evaluation.experiments", "evaluation.targets"),
        "targets": ("evaluation.evaluators",),
    }
    violations: dict[str, list[str]] = {}
    for area, forbidden_prefixes in forbidden_by_area.items():
        for path in (EVALUATION_ROOT / area).glob("*.py"):
            bad_imports = sorted(
                imported for imported in _imports(path) if imported.startswith(forbidden_prefixes)
            )
            if bad_imports:
                violations[str(path.relative_to(BACKEND_ROOT))] = bad_imports

    assert violations == {}
