"""The v2 scripted target validates outreach without rewriting historical inputs."""

import json
from typing import cast

from app.features.prospect_intelligence.contracts.models import OutreachDraft
from app.features.prospect_intelligence.domain.outreach import validate_customer_outreach
from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.datasets import langsmith_examples
from evaluation.targets.scenario import scenario_artifacts
from evaluation.targets.scenario_identity import synthetic_v2_identity


def test_every_scripted_fit_draft_satisfies_outreach_v2() -> None:
    checked = 0
    for example in langsmith_examples():
        assert example.inputs is not None
        artifacts = scenario_artifacts(example.inputs)
        analysis = cast(
            "dict[str, object]",
            json.loads(artifacts[PROSPECT_FILES.lane_fit_json]),
        )
        lanes = cast("list[dict[str, object]]", analysis["top_lanes"])
        if not lanes:
            assert PROSPECT_FILES.outreach_draft not in artifacts
            continue
        identity = synthetic_v2_identity(example.inputs)
        first, separator, body = artifacts[PROSPECT_FILES.outreach_draft].partition("\n\n")
        assert separator
        validate_customer_outreach(
            OutreachDraft(subject=first.removeprefix("Subject: "), body=body),
            identity.outreach_context(
                str(lanes[0]["origin"]),
                str(lanes[0]["destination"]),
            ),
        )
        checked += 1

    assert checked > 0


def test_v2_identity_projection_does_not_change_historical_example_inputs() -> None:
    example = langsmith_examples()[0]
    assert example.inputs is not None

    identity = synthetic_v2_identity(example.inputs)

    assert example.inputs["account_name"] == "Synthetic Core Shipper 01"
    assert identity.account_name == "Synthetic Core Shipper One"
