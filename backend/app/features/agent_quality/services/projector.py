"""Build bounded online evaluator envelopes from completed graph state."""

import math
from collections.abc import Mapping, Sequence
from uuid import UUID

from app.features.agent_quality.contracts.models import (
    QualityEvaluationEnvelope,
    QualityEvaluationProjection,
    SemanticEvaluationInput,
)
from app.features.agent_quality.domain.deterministic import (
    lane_reference_signals,
    numeric_grounding_signal,
    trajectory_signal,
)
from app.features.agent_quality.domain.projection_runtime import (
    decode_files,
    file_contract_signal,
    informational_signal,
    injection_signal,
    pending_review,
    runtime_projection,
    semantic_inputs,
)
from app.features.agent_quality.domain.sampling import evaluation_sampling_decision
from app.features.agent_quality.domain.semantic_projection import semantic_observations
from app.features.agent_quality.domain.semantic_runtime import semantic_state_items
from app.features.prospect_intelligence.public import AnalysisOutput


class OnlineQualityProjector:
    """Pure application boundary for durable, privacy-safe evaluator input."""

    def __init__(
        self,
        *,
        evaluator_version: str,
        graph_revision: str,
        rubric_version: str,
        evaluation_sample_rate: float = 0.10,
        agent_version: str = "prospect-intelligence-v1",
        prompt_version: str = "v1",
    ) -> None:
        if not math.isfinite(evaluation_sample_rate) or not 0.0 <= evaluation_sample_rate <= 1.0:
            raise ValueError("evaluation sample rate must be finite and between zero and one")
        self._evaluator_version = evaluator_version
        self._graph_revision = graph_revision
        self._rubric_version = rubric_version
        self._evaluation_sample_rate = evaluation_sample_rate
        self._agent_version = agent_version
        self._prompt_version = prompt_version

    def project(
        self,
        *,
        run_id: UUID,
        files: Mapping[str, object],
        raw_state: Mapping[str, object],
        account_name: str,
        rep_preferences: Sequence[str] = (),
        latency_seconds: float,
        analysis_output: AnalysisOutput,
        injection_canary: str | None = None,
    ) -> QualityEvaluationProjection:
        sampling = evaluation_sampling_decision(run_id, self._evaluation_sample_rate)
        if not sampling.selected:
            return QualityEvaluationProjection(sampling=sampling, evaluation=None)
        latency_valid = math.isfinite(latency_seconds) and latency_seconds >= 0
        safe_latency = latency_seconds if latency_valid else 0.0
        artifacts, invalid_encoding = decode_files(files)
        events, tool_names, tool_state_valid = runtime_projection(raw_state.get("messages"))
        projected_semantics: tuple[SemanticEvaluationInput, ...] = ()
        semantic_projection_valid = True
        try:
            observations = semantic_observations(
                artifacts,
                account_name=account_name,
                rep_preferences=rep_preferences,
                injection_canary=injection_canary,
            )
            projected_semantics = semantic_inputs(
                semantic_state_items(observations),
                expected_next_step=analysis_output.brief.recommended_next_step.value,
            )
        except (TypeError, ValueError):
            semantic_projection_valid = False
        reference_signals = lane_reference_signals(artifacts, analysis_output)
        file_signal = file_contract_signal(
            files,
            artifacts,
            invalid_encoding=invalid_encoding,
        )
        return QualityEvaluationProjection(
            sampling=sampling,
            evaluation=QualityEvaluationEnvelope(
                evaluator_version=self._evaluator_version,
                graph_revision=self._graph_revision,
                rubric_version=self._rubric_version,
                agent_version=self._agent_version,
                prompt_version=self._prompt_version,
                deterministic_signals=(
                    numeric_grounding_signal(artifacts),
                    *reference_signals,
                    file_signal,
                    trajectory_signal(
                        events,
                        pending_review=pending_review(raw_state),
                        latency_seconds=safe_latency,
                    ),
                    injection_signal(
                        artifacts,
                        tool_names,
                        tool_state_valid=tool_state_valid,
                        semantic_projection_valid=semantic_projection_valid,
                        canary=injection_canary,
                    ),
                    informational_signal("latency_seconds", safe_latency, latency_valid, 300.0),
                    informational_signal("cost_usd", None, False, 1_000.0, unavailable_ok=True),
                    informational_signal(
                        "tool_call_count", float(len(tool_names)), tool_state_valid, 1_000.0
                    ),
                ),
                semantic_inputs=projected_semantics,
            ),
        )
