"""Application-owned projection from graph state into bounded evaluator input."""

import json
import math
from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.features.agent_quality.contracts.online_config import OnlineQualityConfig, OnlineRule
from app.features.agent_quality.domain.deterministic import (
    numeric_grounding_signal,
    trajectory_signal,
)
from app.features.agent_quality.domain.sampling import (
    EVALUATION_SAMPLING_POLICY_VERSION,
    evaluation_sampling_decision,
)
from app.features.agent_quality.domain.semantic_projection import citation_id
from app.features.agent_quality.public import EVALUATOR_VERSION
from app.features.agent_quality.services.projector import OnlineQualityProjector
from app.features.prospect_intelligence.public import (
    PROSPECT_FILES,
    AnalysisOutput,
    LaneAnalysisArtifact,
    ProspectBrief,
    RecommendedNextStep,
    ScoredLane,
)
from evaluation.evaluators.numeric_grounding import evaluate_numeric_grounding
from evaluation.evaluators.trajectory import evaluate_trajectory
from tests.unit.evaluation.support import artifacts, outputs


def _files(values: Mapping[str, str]) -> dict[str, object]:
    return {path: {"encoding": "utf-8", "content": content} for path, content in values.items()}


def _artifacts() -> dict[str, str]:
    values = artifacts()
    for path in (
        PROSPECT_FILES.account_context,
        PROSPECT_FILES.network_context,
        PROSPECT_FILES.company_research,
        PROSPECT_FILES.freight_research,
        PROSPECT_FILES.market_research,
    ):
        source = cast("dict[str, object]", json.loads(values[path]))
        evidence = cast("list[dict[str, object]]", source["evidence"])
        provenance = cast("dict[str, object]", evidence[0]["provenance"])
        provenance["source"] = path
        values[path] = json.dumps(source)
    return values


def _raw_state(*, messages: object | None = None) -> dict[str, object]:
    if messages is None:
        messages = [
            HumanMessage(content="Run the synthetic prospect workflow."),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {"subagent_type": specialist},
                        "id": f"call-{index}",
                        "type": "tool_call",
                    }
                    for index, specialist in enumerate(
                        (
                            "account-context",
                            "external-research",
                            "lane-analyst",
                            "outreach-drafter",
                            "quality-reviewer",
                        )
                    )
                ]
                + [
                    {
                        "name": "send_outreach",
                        "args": {},
                        "id": "call-review",
                        "type": "tool_call",
                    }
                ],
            ),
        ]
    return {"messages": messages, "review_requested": {"name": "send_outreach"}}


RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


def _projector(*, sample_rate: float = 1.0) -> OnlineQualityProjector:
    return OnlineQualityProjector(
        evaluator_version=EVALUATOR_VERSION,
        graph_revision="prospect-graph-v1",
        rubric_version="semantic-v1",
        evaluation_sample_rate=sample_rate,
    )


def _analysis_output(values: Mapping[str, str]) -> AnalysisOutput:
    artifact = LaneAnalysisArtifact.from_json(values[PROSPECT_FILES.lane_fit_json])
    return AnalysisOutput(
        verdict=artifact.verdict,
        brief=ProspectBrief(
            summary="Synthetic",
            markdown=values[PROSPECT_FILES.sales_brief],
            recommended_next_step=RecommendedNextStep.NEW_LANE_PITCH,
            recommendation="Review synthetic evidence.",
            lanes=tuple(ScoredLane(score=lane, evidence=()) for lane in artifact.top_lanes),
        ),
        outreach=None,
        source_coverage=(),
    )


def test_online_quality_config_validates_one_finite_cohort_sample_rate() -> None:
    config = OnlineQualityConfig.default()

    assert config.evaluation_sample_rate == 0.10
    assert all(not hasattr(rule, "sample_rate") for rule in config.rules)
    assert OnlineRule("numeric_groundedness").annotation_on_failure is True

    for invalid in (-0.01, 1.01, math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="sample rate"):
            OnlineQualityConfig(
                project_name=config.project_name,
                annotation_queue=config.annotation_queue,
                evaluation_sample_rate=invalid,
                rules=config.rules,
                alerts=config.alerts,
                dashboard_metrics=config.dashboard_metrics,
            )
        with pytest.raises(ValueError, match="sample rate"):
            _projector(sample_rate=invalid)


def test_sampling_boundaries_and_fixed_uuid_cohorts_are_deterministic() -> None:
    first = UUID("00000000-0000-0000-0000-000000000001")
    second = UUID("00000000-0000-0000-0000-000000000002")

    assert evaluation_sampling_decision(first, 0.0).selected is False
    assert evaluation_sampling_decision(first, 1.0).selected is True
    assert evaluation_sampling_decision(first, 0.10) == evaluation_sampling_decision(first, 0.10)
    assert evaluation_sampling_decision(first, 0.10).selected is False
    assert evaluation_sampling_decision(second, 0.10).selected is True
    assert evaluation_sampling_decision(first, 0.10).policy_version == (
        EVALUATION_SAMPLING_POLICY_VERSION
    )


def test_unsampled_projection_bypasses_evaluator_state_projection() -> None:
    decision = _projector(sample_rate=0.0).project(
        run_id=RUN_ID,
        files={"unsafe": object()},
        raw_state={"messages": object()},
        account_name="Synthetic",
        latency_seconds=math.nan,
        analysis_output=_analysis_output(_artifacts()),
    )

    assert decision.sampling.selected is False
    assert decision.sampling.sample_rate == 0.0
    assert decision.evaluation is None


def test_selected_projection_returns_the_complete_evaluator_cohort() -> None:
    values = _artifacts()
    projection = _projector(sample_rate=1.0).project(
        run_id=RUN_ID,
        files=_files(values),
        raw_state=_raw_state(),
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(values),
    )

    assert projection.sampling.selected is True
    assert projection.evaluation is not None
    assert len(projection.evaluation.deterministic_signals) == 10
    assert {item.key for item in projection.evaluation.semantic_inputs} == {
        "claim_supported",
        "internal_data_leak",
        "draft_matches_brief",
        "next_step",
        "entity_resolution_ok",
        "actionability",
        "tone_fit",
    }


def test_projector_matches_offline_numeric_and_trajectory_semantics() -> None:
    values = _artifacts()
    projection = _projector().project(
        run_id=RUN_ID,
        files=_files(values),
        raw_state=_raw_state(),
        account_name="Synthetic",
        rep_preferences=("Prefer concise outreach.",),
        latency_seconds=1.25,
        analysis_output=_analysis_output(values),
    )
    assert projection.evaluation is not None
    envelope = projection.evaluation

    assert [signal.key for signal in envelope.deterministic_signals] == [
        "numeric_groundedness",
        "lane_precision_at_3",
        "analysis_correctness",
        "fit_verdict_accuracy",
        "file_contract",
        "trajectory_checks",
        "injection_resistance",
        "latency_seconds",
        "cost_usd",
        "tool_call_count",
    ]
    signals = {signal.key: signal for signal in envelope.deterministic_signals}
    offline_numeric = evaluate_numeric_grounding(outputs(values), {})
    events = [
        "account_context.completed",
        "external_research.completed",
        "lane_analyst.completed",
        "outreach_drafter.completed",
        "quality_review.completed",
        "review.requested",
    ]
    offline_trajectory = evaluate_trajectory(
        {"trajectory_events": events, "pending_review": True}, {}
    )

    assert signals["numeric_groundedness"].score == offline_numeric.score == 1.0
    assert signals["trajectory_checks"].score == offline_trajectory.score == 1.0
    assert signals["trajectory_checks"].metadata == {
        "violations": [],
        "event_count": 6,
        "latency_seconds": 1.25,
    }
    assert signals["lane_precision_at_3"].score == 1.0
    assert signals["analysis_correctness"].score == 1.0
    assert signals["fit_verdict_accuracy"].score == 1.0
    assert signals["file_contract"].passed is True
    assert signals["injection_resistance"].passed is True
    assert signals["latency_seconds"].score == 1.25
    assert signals["cost_usd"].score is None
    assert signals["cost_usd"].value == "unavailable"
    assert signals["tool_call_count"].score == 6.0
    assert envelope.evaluator_version == EVALUATOR_VERSION
    assert envelope.graph_revision == "prospect-graph-v1"
    assert envelope.rubric_version == "semantic-v1"
    assert envelope.agent_version == "prospect-intelligence-v1"
    assert envelope.prompt_version == "v1"
    assert {item.key for item in envelope.semantic_inputs} == {
        "claim_supported",
        "internal_data_leak",
        "draft_matches_brief",
        "next_step",
        "entity_resolution_ok",
        "actionability",
        "tone_fit",
    }
    assert all(item.instance_id == "default" for item in envelope.semantic_inputs)
    claim = next(item for item in envelope.semantic_inputs if item.key == "claim_supported")
    next_step = next(item for item in envelope.semantic_inputs if item.key == "next_step")
    assert claim.not_applicable is True and claim.state == {}
    assert next_step.expected_value == RecommendedNextStep.NEW_LANE_PITCH.value


def test_deterministic_failures_match_offline_evaluator_semantics() -> None:
    values = _artifacts()
    values[PROSPECT_FILES.sales_brief] += " Published in 2026."
    online_numeric = numeric_grounding_signal(values)
    offline_numeric = evaluate_numeric_grounding(outputs(values), {})
    invalid_events = (
        "lane_analyst.completed",
        "account_context.completed",
        "outreach.sent",
    )
    online_trajectory = trajectory_signal(invalid_events, pending_review=False, latency_seconds=2.0)
    offline_trajectory = evaluate_trajectory(
        {"trajectory_events": list(invalid_events), "pending_review": False}, {}
    )

    assert online_numeric.score == offline_numeric.score == 0.0
    assert online_numeric.metadata["unsupported_values"] == ["2026"]
    assert online_trajectory.score == offline_trajectory.score == 0.0
    offline_metadata = (
        cast("Mapping[str, object] | None", cast("Any", offline_trajectory).metadata) or {}
    )
    assert online_trajectory.metadata["violations"] == offline_metadata["violations"]


def test_projector_ignores_valid_non_ai_messages_when_counting_tools() -> None:
    values = _artifacts()
    state = _raw_state()
    messages = cast("list[object]", state["messages"])
    messages.insert(1, SystemMessage(content="Use the configured specialists."))

    projection = _projector().project(
        run_id=RUN_ID,
        files=_files(values),
        raw_state=state,
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(values),
    )
    assert projection.evaluation is not None
    envelope = projection.evaluation

    signals = {signal.key: signal for signal in envelope.deterministic_signals}
    assert signals["injection_resistance"].passed is True
    assert signals["tool_call_count"].score == 6.0


def test_projector_assigns_stable_instances_to_repeated_semantic_criteria() -> None:
    values = _artifacts()
    source = cast("dict[str, object]", json.loads(values[PROSPECT_FILES.freight_research]))
    evidence = cast("list[dict[str, object]]", source["evidence"])
    provenance = cast("dict[str, object]", evidence[0]["provenance"])
    identifier = citation_id(provenance)
    values[PROSPECT_FILES.sales_brief] = (
        "## Evidence-backed claims\n"
        f"- Reviewed freight evidence supports a conversation. [{identifier}]\n"
        f"- Reviewed freight evidence indicates a viable fit. [{identifier}]\n"
    )
    files = _files(values)
    state = _raw_state()
    first_projection = _projector().project(
        run_id=RUN_ID,
        files=files,
        raw_state=state,
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(values),
    )
    second_projection = _projector().project(
        run_id=RUN_ID,
        files=files,
        raw_state=state,
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(values),
    )
    assert first_projection.evaluation is not None
    assert second_projection.evaluation is not None
    first = first_projection.evaluation
    second = second_projection.evaluation
    first_claims = [item for item in first.semantic_inputs if item.key == "claim_supported"]
    second_claims = [item for item in second.semantic_inputs if item.key == "claim_supported"]

    assert len(first_claims) == 2
    assert all(item.instance_id != "default" for item in first_claims)
    assert len({item.instance_id for item in first_claims}) == 2
    assert [item.instance_id for item in first_claims] == [
        item.instance_id for item in second_claims
    ]
    assert not any(item.not_applicable for item in first_claims)
    assert next(item for item in first.semantic_inputs if item.key == "tone_fit").not_applicable


def test_projector_records_missing_or_malformed_artifacts_without_raising() -> None:
    missing = _artifacts()
    del missing[PROSPECT_FILES.sales_brief]

    projection = _projector().project(
        run_id=RUN_ID,
        files=_files(missing),
        raw_state=_raw_state(),
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(_artifacts()),
    )
    assert projection.evaluation is not None
    envelope = projection.evaluation
    signal = next(item for item in envelope.deterministic_signals if item.key == "file_contract")
    assert signal.passed is False
    assert signal.metadata["missing_count"] == 1
    injection = next(
        item for item in envelope.deterministic_signals if item.key == "injection_resistance"
    )
    assert injection.metadata["semantic_projection_valid"] is False

    projection = _projector().project(
        run_id=RUN_ID,
        files={PROSPECT_FILES.sales_brief: {"encoding": "base64", "content": "eA=="}},
        raw_state=_raw_state(),
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(_artifacts()),
    )
    assert projection.evaluation is not None
    envelope = projection.evaluation
    signal = next(item for item in envelope.deterministic_signals if item.key == "file_contract")
    assert signal.passed is False
    assert signal.metadata["invalid_encoding_count"] == 1


def test_projector_ignores_the_scoped_rep_memory_file_in_artifact_contract() -> None:
    values = _artifacts()
    files = _files(values)
    files[PROSPECT_FILES.rep_memory("tenant-demo", "rep-demo")] = {
        "encoding": "utf-8",
        "content": "Prefer concise outreach.",
    }

    projection = _projector().project(
        run_id=RUN_ID,
        files=files,
        raw_state=_raw_state(),
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(values),
    )
    assert projection.evaluation is not None
    envelope = projection.evaluation

    signal = next(item for item in envelope.deterministic_signals if item.key == "file_contract")
    assert signal.passed is True
    assert signal.metadata["unexpected_count"] == 0
    assert signal.metadata["actual_count"] == len(PROSPECT_FILES.required_artifacts())


def test_projector_records_injection_canary_and_bad_history_without_raising() -> None:
    values = _artifacts()
    values[PROSPECT_FILES.outreach_draft] += " PLANTED-CANARY"
    projection = _projector().project(
        run_id=RUN_ID,
        files=_files(values),
        raw_state=_raw_state(),
        account_name="Synthetic",
        latency_seconds=1.0,
        injection_canary="planted-canary",
        analysis_output=_analysis_output(values),
    )
    assert projection.evaluation is not None
    envelope = projection.evaluation
    injection = next(
        signal for signal in envelope.deterministic_signals if signal.key == "injection_resistance"
    )
    assert injection.passed is False
    assert injection.metadata == {
        "forbidden_tool_count": 0,
        "canary_found": True,
        "tool_state_valid": True,
        "semantic_projection_valid": False,
    }
    file_contract = next(
        signal for signal in envelope.deterministic_signals if signal.key == "file_contract"
    )
    assert file_contract.passed is True

    values = _artifacts()
    projection = _projector().project(
        run_id=RUN_ID,
        files=_files(values),
        raw_state=_raw_state(messages="not-a-message-sequence"),
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(values),
    )
    assert projection.evaluation is not None
    envelope = projection.evaluation
    trajectory = next(
        signal for signal in envelope.deterministic_signals if signal.key == "trajectory_checks"
    )
    assert trajectory.passed is False
    assert trajectory.metadata["violations"] == [
        "missing stages: account_context.completed, external_research.completed, "
        "lane_analyst.completed, outreach_drafter.completed, quality_review.completed, "
        "review.requested"
    ]


def test_semantic_claim_bound_does_not_change_the_file_contract_result() -> None:
    values = _artifacts()
    source = cast("dict[str, object]", json.loads(values[PROSPECT_FILES.freight_research]))
    evidence = cast("list[dict[str, object]]", source["evidence"])
    provenance = cast("dict[str, object]", evidence[0]["provenance"])
    identifier = citation_id(provenance)
    values[PROSPECT_FILES.sales_brief] = "## Evidence-backed claims\n" + "\n".join(
        f"- Qualitative freight claim {index} is supported. [{identifier}]" for index in range(9)
    )

    projection = _projector().project(
        run_id=RUN_ID,
        files=_files(values),
        raw_state=_raw_state(),
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(values),
    )
    assert projection.evaluation is not None
    envelope = projection.evaluation

    signals = {signal.key: signal for signal in envelope.deterministic_signals}
    assert signals["file_contract"].passed is True
    assert signals["injection_resistance"].passed is False
    assert signals["injection_resistance"].metadata["semantic_projection_valid"] is False
    assert envelope.semantic_inputs == ()


def test_serialized_envelope_excludes_raw_artifact_and_source_bodies() -> None:
    values = _artifacts()
    source = cast("dict[str, object]", json.loads(values[PROSPECT_FILES.freight_research]))
    source["private_customer_payload"] = "RAW-SOURCE-BODY-MUST-NOT-LEAVE"
    values[PROSPECT_FILES.freight_research] = json.dumps(source)
    values[PROSPECT_FILES.task_brief] = "RAW-TASK-BODY-MUST-NOT-LEAVE"
    projection = _projector().project(
        run_id=RUN_ID,
        files=_files(values),
        raw_state=_raw_state(),
        account_name="Synthetic",
        latency_seconds=1.0,
        analysis_output=_analysis_output(values),
    )
    assert projection.evaluation is not None
    envelope = projection.evaluation

    rendered = json.dumps(envelope.to_payload(), sort_keys=True)
    assert "RAW-SOURCE-BODY-MUST-NOT-LEAVE" not in rendered
    assert "RAW-TASK-BODY-MUST-NOT-LEAVE" not in rendered
    assert "private_customer_payload" not in rendered
    assert PROSPECT_FILES.freight_research not in rendered
