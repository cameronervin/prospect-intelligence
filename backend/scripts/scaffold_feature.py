"""Create a feature package that follows the repository architecture contract."""

import argparse
import re
from collections.abc import Sequence
from pathlib import Path

FEATURE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
LAYERS = (
    "api",
    "services",
    "agents",
    "domain",
    "models",
    "schemas",
    "repositories",
    "integrations",
    "contracts",
)


def validate_feature_name(name: str) -> str:
    """Return a safe snake_case feature name or raise a useful error."""

    if not FEATURE_NAME.fullmatch(name):
        raise ValueError(
            "feature name must be lower snake_case, start with a letter, "
            "and contain no paths or repeated underscores"
        )
    return name


def feature_files(name: str) -> dict[Path, str]:
    """Return the complete file contract for one feature."""

    title = name.replace("_", " ")
    files = {
        Path("__init__.py"): (
            f'"""{title.capitalize()} feature boundary.\n\n'
            "Expose cross-feature behavior through public.py or contracts only.\n"
            '"""\n'
        ),
        Path("public.py"): (
            f'"""Supported cross-feature interface for {title}.\n\n'
            "Add exports only when another feature has a concrete consumer.\n"
            '"""\n'
        ),
    }
    for layer in LAYERS:
        label = layer.replace("_", " ")
        files[Path(layer) / "__init__.py"] = f'"""{title.capitalize()} {label} layer."""\n'
    return files


def create_feature(name: str, *, root: Path, dry_run: bool = False) -> list[Path]:
    """Create one feature atomically enough to refuse ambiguous overwrites."""

    safe_name = validate_feature_name(name)
    resolved_root = root.resolve()
    target = (resolved_root / safe_name).resolve()
    if target.parent != resolved_root:
        raise ValueError("feature target must remain inside the feature root")
    if target.exists():
        raise FileExistsError(f"feature already exists: {target}")

    files = feature_files(safe_name)
    paths = [target / relative for relative in files]
    if dry_run:
        return paths

    target.mkdir(parents=True, exist_ok=False)
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return paths


def parser() -> argparse.ArgumentParser:
    feature_root = Path(__file__).resolve().parents[1] / "app" / "features"
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("name", help="lower snake_case feature name")
    argument_parser.add_argument("--dry-run", action="store_true", help="print without writing")
    argument_parser.add_argument("--root", type=Path, default=feature_root, help=argparse.SUPPRESS)
    return argument_parser


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        paths = create_feature(args.name, root=args.root, dry_run=args.dry_run)
    except (ValueError, FileExistsError) as error:
        parser().error(str(error))
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
