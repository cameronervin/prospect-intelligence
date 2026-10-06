"""Static enforcement for modular-monolith dependency boundaries."""

import ast
from importlib import import_module
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
FEATURE_ROOT = APP_ROOT / "features"
FEATURE_PREFIX = "app.features."
MAX_APPLICATION_MODULE_LINES = 250
PROSPECT_AGENT_ROOT = FEATURE_ROOT / "prospect_intelligence" / "agents"


def imports(path: Path, app_root: Path = APP_ROOT) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    module_parts = path.relative_to(app_root.parent).with_suffix("").parts
    package_parts = module_parts[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module)
                continue
            parent_count = max(node.level - 1, 0)
            base = package_parts[: len(package_parts) - parent_count]
            imported = tuple(node.module.split(".")) if node.module else ()
            found.add(".".join((*base, *imported)))
    return found


def python_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]


def test_prospect_agent_tools_use_a_narrow_package_surface() -> None:
    tools_package = PROSPECT_AGENT_ROOT / "tools"

    assert tools_package.is_dir()
    assert (tools_package / "__init__.py").is_file()
    assert not {
        path.name
        for path in (
            PROSPECT_AGENT_ROOT / "tools.py",
            PROSPECT_AGENT_ROOT / "artifact_tools.py",
            PROSPECT_AGENT_ROOT / "tool_support.py",
            PROSPECT_AGENT_ROOT / "errors.py",
        )
        if path.exists()
    }
    tools = import_module("app.features.prospect_intelligence.agents.tools")
    assert tools.__all__ == ["ToolRegistry", "build_tool_registry"]


def test_platform_and_shared_kernel_do_not_depend_on_features() -> None:
    violations = {
        str(path.relative_to(APP_ROOT)): sorted(
            imported for imported in imports(path) if imported.startswith(FEATURE_PREFIX)
        )
        for root in (APP_ROOT / "platform", APP_ROOT / "shared_kernel")
        for path in python_files(root)
    }

    assert not {path: imported for path, imported in violations.items() if imported}


def test_model_provider_implementation_is_platform_owned() -> None:
    forbidden_roots = (APP_ROOT / "bootstrap", FEATURE_ROOT / "prospect_intelligence")
    violations = {
        str(path.relative_to(APP_ROOT)): sorted(
            imported
            for imported in imports(path)
            if imported.startswith(("langchain_openai", "openai"))
        )
        for root in forbidden_roots
        for path in python_files(root)
    }

    assert not {path: imported for path, imported in violations.items() if imported}


def test_prospect_agent_implementation_is_not_in_bootstrap() -> None:
    forbidden = {
        APP_ROOT / "bootstrap" / "agent_factory.py",
        APP_ROOT / "bootstrap" / "prospect_agent_handler.py",
        APP_ROOT / "bootstrap" / "prospect_workers.py",
    }

    assert not {str(path.relative_to(APP_ROOT)) for path in forbidden if path.exists()}


def test_cross_feature_imports_use_public_contracts() -> None:
    violations: list[str] = []
    for path in python_files(FEATURE_ROOT):
        relative = path.relative_to(FEATURE_ROOT)
        if len(relative.parts) < 2:
            continue
        source_feature = relative.parts[0]
        for imported in imports(path):
            if not imported.startswith(FEATURE_PREFIX):
                continue
            remainder = imported.removeprefix(FEATURE_PREFIX)
            parts = remainder.split(".")
            target_feature = parts[0]
            if target_feature == source_feature:
                continue
            if len(parts) < 2 or parts[1] not in {"public", "contracts"}:
                violations.append(f"{relative}: {imported}")

    assert not violations


def test_relative_cross_feature_import_resolves_to_internal_module(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    module = app_root / "features" / "source" / "api" / "module.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from ...other_feature.repositories import UnsafeRepository\n",
        encoding="utf-8",
    )

    assert "app.features.other_feature.repositories" in imports(module, app_root)


def test_feature_layers_follow_dependency_direction() -> None:
    forbidden = {
        "api": ("sqlalchemy", ".models", ".repositories", ".integrations"),
        "services": (
            "fastapi",
            "starlette",
            "sqlalchemy",
            ".api",
            ".agents",
            ".models",
            ".repositories",
            ".integrations",
        ),
        "agents": (
            "fastapi",
            "starlette",
            "sqlalchemy",
            ".api",
            ".services",
            ".models",
            ".repositories",
            ".integrations",
        ),
        "domain": (
            "fastapi",
            "starlette",
            "pydantic",
            "sqlalchemy",
            ".api",
            ".services",
            ".agents",
            ".models",
            ".repositories",
            ".integrations",
        ),
        "schemas": ("fastapi", "starlette", "sqlalchemy"),
        "models": ("fastapi", "starlette", ".api", ".services", ".agents"),
        "repositories": ("fastapi", "starlette", ".api", ".services", ".agents"),
        "integrations": (
            "fastapi",
            "starlette",
            "sqlalchemy",
            ".api",
            ".services",
            ".agents",
            ".models",
            ".repositories",
        ),
        "contracts": (
            "fastapi",
            "starlette",
            "sqlalchemy",
            ".api",
            ".services",
            ".agents",
            ".models",
            ".repositories",
            ".integrations",
        ),
    }
    violations: list[str] = []
    for feature in FEATURE_ROOT.iterdir():
        if not feature.is_dir() or feature.name.startswith("__"):
            continue
        prefix = f"{FEATURE_PREFIX}{feature.name}"
        for layer, blocked in forbidden.items():
            layer_root = feature / layer
            if not layer_root.exists():
                continue
            for path in python_files(layer_root):
                for imported in imports(path):
                    relative_import = (
                        imported.removeprefix(prefix) if imported.startswith(prefix) else imported
                    )
                    if imported.startswith(blocked) or relative_import.startswith(blocked):
                        violations.append(f"{path.relative_to(APP_ROOT)}: {imported}")

    assert not violations


def test_application_modules_stay_reviewable() -> None:
    oversized = {
        str(path.relative_to(APP_ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in python_files(APP_ROOT)
        if len(path.read_text(encoding="utf-8").splitlines()) > MAX_APPLICATION_MODULE_LINES
    }

    assert not oversized
