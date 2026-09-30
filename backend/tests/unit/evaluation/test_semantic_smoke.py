"""Explicit-live guard and sanitized output for the CAM-39 smoke."""

from collections.abc import Sequence

import pytest
from pydantic import SecretStr

from app.platform.config.settings import Settings
from evaluation.experiments.semantic_smoke import SmokeSummary, main


def _settings(*, typesafe: str | None, openai: str | None) -> Settings:
    return Settings(
        typesafe_api_key=SecretStr(typesafe) if typesafe is not None else None,
        openai_api_key=SecretStr(openai) if openai is not None else None,
    )


def test_smoke_requires_explicit_live_flag() -> None:
    with pytest.raises(SystemExit, match="2"):
        main([], settings_factory=lambda: _settings(typesafe="jev-secret", openai="oa-secret"))


@pytest.mark.parametrize(
    ("typesafe", "openai", "missing"),
    [
        (None, "oa-secret", "TYPESAFE_API_KEY"),
        ("jev-secret", None, "OPENAI_API_KEY"),
    ],
)
def test_smoke_rejects_missing_credentials(
    typesafe: str | None,
    openai: str | None,
    missing: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(
        ["--live"],
        settings_factory=lambda: _settings(typesafe=typesafe, openai=openai),
    )

    assert result == 2
    assert missing in capsys.readouterr().err


def test_smoke_prints_only_sanitized_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    received: list[Sequence[str]] = []

    async def fake_runner(typesafe_key: str, openai_key: str) -> SmokeSummary:
        received.append((typesafe_key, openai_key))
        return SmokeSummary(jev_rows=1, comparison_rows=1, explanation_received=True)

    result = main(
        ["--live"],
        settings_factory=lambda: _settings(typesafe="jev-secret", openai="oa-secret"),
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert received == [("jev-secret", "oa-secret")]
    assert captured.out == (
        "CAM-39 live smoke: PASS; jev_rows=1; comparison_rows=1; explanation_received=true\n"
    )
    assert "secret" not in captured.out + captured.err
