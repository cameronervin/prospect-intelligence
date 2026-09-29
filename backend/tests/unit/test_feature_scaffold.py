"""Feature generator behavior tests."""

from pathlib import Path

import pytest

from scripts.scaffold_feature import LAYERS, create_feature, validate_feature_name


@pytest.mark.parametrize(
    "name",
    ["../escape", "nested/path", "UpperCase", "double__underscore", "trailing_", "1prefix"],
)
def test_generator_rejects_unsafe_or_invalid_names(name: str) -> None:
    with pytest.raises(ValueError):
        validate_feature_name(name)


def test_dry_run_reports_complete_contract_without_writing(tmp_path: Path) -> None:
    paths = create_feature("case_management", root=tmp_path, dry_run=True)

    assert not (tmp_path / "case_management").exists()
    assert tmp_path / "case_management" / "public.py" in paths
    assert all(tmp_path / "case_management" / layer / "__init__.py" in paths for layer in LAYERS)


def test_generator_creates_layers_and_refuses_overwrite(tmp_path: Path) -> None:
    paths = create_feature("case_management", root=tmp_path)

    assert all(path.is_file() for path in paths)
    assert "cross-feature" in (tmp_path / "case_management" / "public.py").read_text()
    with pytest.raises(FileExistsError):
        create_feature("case_management", root=tmp_path)
