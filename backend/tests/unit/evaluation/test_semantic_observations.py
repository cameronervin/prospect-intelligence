"""Privacy and provenance contracts for semantic-judge projections."""

import json
from collections.abc import Mapping
from typing import cast

import pytest

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.contracts.semantic import (
    citation_id,
    semantic_observations,
)


def _provenance(**overrides: str) -> dict[str, str]:
    return {
        "source": "synthetic",
        "mode": "fixture",
        "endpoint_or_artifact": "fixture://synthetic",
        "retrieved_at": "2026-09-29T00:00:00+00:00",
        "evidence_location": "record:1",
        "source_version": "v1",
        **overrides,
    }


def _source(path: str, *, values: Mapping[str, object] | None = None) -> tuple[str, str]:
    provenance = _provenance(source=path)
    payload = {
        **(values or {}),
        "coverage": {"source": "synthetic", "status": "complete"},
        "evidence": [
            {
                "claim": "UNTRUSTED-RAW-CLAIM",
                "citation_id": citation_id(provenance),
                "provenance": provenance,
            }
        ],
    }
    return path, json.dumps(payload)


def _artifacts(brief: str) -> dict[str, str]:
    return dict(
        (
            _source(
                PROSPECT_FILES.account_context,
                values={
                    "account_name": "Acme Foods",
                    "headquarters": "Chicago, IL",
                    "industry": "Food",
                    "relationship": "Prospect",
                },
            ),
            _source(PROSPECT_FILES.network_context),
            _source(PROSPECT_FILES.company_research),
            _source(PROSPECT_FILES.freight_research),
            _source(PROSPECT_FILES.market_research),
            (PROSPECT_FILES.lane_fit_json, json.dumps({"verdict": "fit"})),
            (PROSPECT_FILES.sales_brief, brief),
            (PROSPECT_FILES.outreach_draft, "Subject: Freight fit\n\nCould we compare notes?"),
        )
    )


def test_citation_id_is_stable_canonical_and_provenance_sensitive() -> None:
    provenance = _provenance()
    reordered = dict(reversed(tuple(provenance.items())))

    first = citation_id(provenance)

    assert first == citation_id(reordered)
    assert first.startswith("ev_") and len(first) == 27
    assert first != citation_id(_provenance(evidence_location="record:2"))


def test_semantic_observations_are_bounded_and_contain_no_raw_source_content() -> None:
    freight_citation = citation_id(_provenance(source=PROSPECT_FILES.freight_research))
    artifacts = _artifacts(
        "# Sales brief\n\n## Evidence-backed claims\n"
        f"- Reviewed freight evidence supports a conversation. [{freight_citation}]\n\n"
        "## Recommended next step\nnew_lane_pitch\n"
    )

    observations = semantic_observations(
        artifacts,
        account_name="Acme Foods",
        rep_preferences=("Prefer concise outreach.",),
    )

    assert set(observations) == {
        "claim_supported",
        "internal_data_leak",
        "draft_matches_brief",
        "next_step",
        "entity_resolution_ok",
        "actionability",
        "tone_fit",
    }
    claims = cast("list[Mapping[str, object]]", observations["claim_supported"])
    assert claims == [
        {
            "claim": "Reviewed freight evidence supports a conversation.",
            "excerpt": (
                "Reviewed freight research describes prospect-demand inputs for deterministic "
                f"analysis. Evidence record: {freight_citation}."
            ),
            "citation_ids": [freight_citation],
        }
    ]
    assert observations["entity_resolution_ok"] == {
        "account_name": "Acme Foods",
        "resolved_profile": (
            "Account name: Acme Foods; headquarters: Chicago, IL; industry: Food; "
            "relationship: Prospect."
        ),
    }
    assert observations["tone_fit"] == {
        "draft": "Subject: Freight fit\n\nCould we compare notes?",
        "rep_preferences": "Prefer concise outreach.",
    }
    rendered = repr(observations)
    assert "UNTRUSTED-RAW-CLAIM" not in rendered
    assert "fixture://synthetic" not in rendered


def test_single_source_citation_resolves_only_its_own_support() -> None:
    freight_citation = citation_id(_provenance(source=PROSPECT_FILES.freight_research))
    observations = semantic_observations(
        _artifacts(
            "## Evidence-backed claims\n"
            f"- Freight evidence establishes capacity overlap. [{freight_citation}]\n"
        ),
        account_name="Acme Foods",
    )

    excerpt = observations["claim_supported"][0]["excerpt"]
    assert freight_citation in excerpt
    assert "prospect-demand" in excerpt
    assert "carrier-capacity" not in excerpt
    assert "overlap" not in excerpt


def test_semantic_observations_reject_unknown_citations_canaries_and_oversized_state() -> None:
    unknown = "ev_" + ("0" * 24)
    with pytest.raises(ValueError, match="unknown evidence citation"):
        semantic_observations(
            _artifacts(f"## Evidence-backed claims\n- Unsupported claim. [{unknown}]\n"),
            account_name="Acme Foods",
        )

    freight_citation = citation_id(_provenance(source=PROSPECT_FILES.freight_research))
    with pytest.raises(ValueError, match="canary"):
        semantic_observations(
            _artifacts(
                "## Evidence-backed claims\n"
                f"- PLANTED-CANARY supports this claim. [{freight_citation}]\n"
            ),
            account_name="Acme Foods",
            injection_canary="planted-canary",
        )

    artifacts = _artifacts("x" * 6_001)
    with pytest.raises(ValueError, match="brief exceeds"):
        semantic_observations(artifacts, account_name="Acme Foods")


def test_numeric_and_date_claims_are_excluded_from_semantic_judging() -> None:
    freight_citation = citation_id(_provenance(source=PROSPECT_FILES.freight_research))
    observations = semantic_observations(
        _artifacts(
            "## Evidence-backed claims\n"
            f"- The account has 12 weekly loads. [{freight_citation}]\n"
            f"- The 2026 review found a viable fit. [{freight_citation}]\n"
            f"- Its 3PL capability and SOC 2 posture are mature. [{freight_citation}]\n"
            f"- Reviewed evidence indicates a viable fit. [{freight_citation}]\n"
        ),
        account_name="Acme Foods",
    )

    claims = cast("list[Mapping[str, object]]", observations["claim_supported"])
    assert [claim["claim"] for claim in claims] == [
        "Its 3PL capability and SOC 2 posture are mature.",
        "Reviewed evidence indicates a viable fit.",
    ]


def test_semantic_observations_bound_qualitative_claim_fanout() -> None:
    freight_citation = citation_id(_provenance(source=PROSPECT_FILES.freight_research))
    claims = "\n".join(
        f"- Qualitative claim letter {chr(65 + index)} is supported. [{freight_citation}]"
        for index in range(9)
    )

    with pytest.raises(ValueError, match="8-claim bound"):
        semantic_observations(
            _artifacts(f"## Evidence-backed claims\n{claims}\n"),
            account_name="Acme Foods",
        )
