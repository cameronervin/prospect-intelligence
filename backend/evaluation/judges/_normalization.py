"""Compatibility exports for application-owned judge response normalization."""

from app.features.agent_quality.integrations._judge_normalization import (
    attribute,
    normalize_response,
    question_payload,
)

__all__ = ["attribute", "normalize_response", "question_payload"]
