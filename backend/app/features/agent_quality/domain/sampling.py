"""Stable run-level cohort sampling for online evaluation."""

import hashlib
import math
from uuid import UUID

from app.features.agent_quality.contracts.models import EvaluationSamplingDecision

EVALUATION_SAMPLING_POLICY_VERSION = "sha256-run-id-v1"
_BUCKET_DENOMINATOR = 1 << 64


def evaluation_sampling_decision(
    run_id: UUID,
    sample_rate: float,
) -> EvaluationSamplingDecision:
    """Assign one product run to a stable evaluator cohort across retries and replicas."""

    if not math.isfinite(sample_rate) or not 0.0 <= sample_rate <= 1.0:
        raise ValueError("evaluation sample rate must be finite and between zero and one")
    if sample_rate == 0.0:
        selected = False
    elif sample_rate == 1.0:
        selected = True
    else:
        material = f"{EVALUATION_SAMPLING_POLICY_VERSION}:{run_id}".encode()
        bucket = int.from_bytes(hashlib.sha256(material).digest()[:8], byteorder="big")
        selected = bucket / _BUCKET_DENOMINATOR < sample_rate
    return EvaluationSamplingDecision(
        selected=selected,
        sample_rate=sample_rate,
        policy_version=EVALUATION_SAMPLING_POLICY_VERSION,
    )
