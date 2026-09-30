"""Scenario-aware artifact generation for the scripted graph target."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from typing import cast

from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from app.features.prospect_intelligence.public import (
    FitVerdict,
    LaneFitResult,
    NetworkLane,
    ShipperLane,
    rank_lane_fits,
)
from evaluation.contracts.semantic import citation_id

_COVERAGE_STATES = frozenset({"complete", "degraded", "unavailable"})


def _provenance(source: str) -> dict[str, str]:
    return {
        "source": source,
        "mode": "fixture",
        "endpoint_or_artifact": f"fixture://{source}",
        "retrieved_at": "2026-09-29T00:00:00+00:00",
        "evidence_location": "record:1",
        "source_version": "freight-prospect-v1",
    }


def _source_artifact(payload: Mapping[str, object], *, source: str) -> str:
    raw_coverage = payload.get("coverage", "complete")
    coverage = raw_coverage if raw_coverage in _COVERAGE_STATES else "unknown"
    value = {
        **payload,
        "coverage": {
            "source": source,
            "status": coverage,
            "dependency_failed": payload.get("dependency_error") not in (None, ""),
        },
        "evidence": [
            {
                "claim": f"Synthetic evidence supplied by {source}.",
                "citation_id": citation_id(_provenance(source)),
                "provenance": _provenance(source),
            }
        ],
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _records(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("lane inputs must be arrays")
    records = cast("Sequence[object]", value)
    if any(not isinstance(item, Mapping) for item in records):
        raise ValueError("lane inputs must contain objects")
    return tuple(cast("Mapping[str, object]", item) for item in records)


def _text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be text")
    return value


def _integer(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("numeric input is invalid")
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("numeric input is invalid") from error


def _runtime_lane_fit(
    payload: Mapping[str, object],
) -> tuple[FitVerdict, tuple[LaneFitResult, ...]]:
    try:
        crm = cast("Mapping[str, object]", payload["crm"])
        freight = cast("Mapping[str, object]", payload["genlogs"])
        network = cast("Mapping[str, object]", payload["carrier_network"])
        if (
            freight.get("coverage") != "complete"
            or freight.get("dependency_error") is not None
            or len(_records(crm.get("entity_candidates", ()))) > 1
        ):
            return FitVerdict.NEEDS_MORE_DATA, ()
        raw_shippers = _records(freight.get("lanes"))
        if not raw_shippers:
            return FitVerdict.NEEDS_MORE_DATA, ()
        shippers = tuple(
            ShipperLane(
                origin=_text(item, "origin"),
                destination=_text(item, "destination"),
                weekly_loads=_integer(item, "weekly_loads"),
                equipment=_text(item, "equipment"),
                estimated_rate=_decimal(item.get("estimated_rate")),
                distance_miles=_integer(item, "distance_miles"),
            )
            for item in raw_shippers
        )
        networks = tuple(
            NetworkLane(
                origin=_text(item, "origin"),
                destination=_text(item, "destination"),
                weekly_loads=_integer(item, "weekly_loads"),
                empty_capacity=_integer(item, "empty_capacity"),
                fleet_equipment_share={
                    str(name): _decimal(share)
                    for name, share in cast(
                        "Mapping[object, object]", item["fleet_equipment_share"]
                    ).items()
                },
            )
            for item in _records(network.get("lanes"))
        )
        lanes = rank_lane_fits(shippers, networks)
    except (KeyError, TypeError, ValueError):
        return FitVerdict.NEEDS_MORE_DATA, ()
    return (FitVerdict.FIT if lanes else FitVerdict.NO_FIT), lanes


def scenario_artifacts(inputs: Mapping[str, object]) -> dict[str, str]:
    payload = cast("Mapping[str, object]", inputs["input_payload"])
    crm = cast("Mapping[str, object]", payload["crm"])
    freight = cast("Mapping[str, object]", payload["genlogs"])
    network = cast("Mapping[str, object]", payload["carrier_network"])
    market = cast("Mapping[str, object]", payload["faf_market"])
    verdict, runtime_lanes = _runtime_lane_fit(payload)
    lanes = [
        {
            **asdict(lane),
            "backhaul_fill": str(lane.backhaul_fill),
            "density": str(lane.density),
            "equipment_match": str(lane.equipment_match),
            "fit_score": str(lane.fit_score),
            "modeled_annual_revenue": str(lane.modeled_annual_revenue),
        }
        for lane in runtime_lanes
    ]
    analysis = {"method_version": "lane_fit_v1", "verdict": verdict.value, "top_lanes": lanes}
    lane_lines = [f"# Lane fit ({verdict.value})"]
    lane_lines.extend(
        f"- {lane['origin']} to {lane['destination']}: "
        f"{lane['matched_loads_per_week']} matched loads; fit score {lane['fit_score']}."
        for lane in lanes
    )
    if lanes:
        top = lanes[0]
        summary = (
            f"The account has {top['matched_loads_per_week']} matched weekly loads "
            f"on {top['origin']} to {top['destination']}."
        )
        qualitative = (
            "Reviewed freight and carrier-network evidence supports a direct lane-overlap "
            "conversation."
        )
        relationship = crm.get("relationship")
        next_step = "expand_existing_lanes" if relationship == "Customer" else "new_lane_pitch"
    elif verdict is FitVerdict.NEEDS_MORE_DATA:
        summary = "Available source coverage does not support a lane recommendation."
        qualitative = "Reviewed source coverage does not support a lane recommendation."
        next_step = "needs_more_data"
    else:
        summary = "Reviewed evidence shows no direct lane overlap with usable capacity."
        qualitative = "Reviewed evidence shows no direct lane overlap with usable capacity."
        next_step = "not_a_fit"
    freight_citation = citation_id(_provenance("genlogs"))
    network_citation = citation_id(_provenance("network"))
    brief = (
        "# Sales brief\n\n"
        f"{summary}\n\n"
        "## Evidence-backed claims\n"
        f"- {qualitative} [{freight_citation}] [{network_citation}]\n\n"
        "## Recommended next step\n"
        f"{next_step}\n"
    )
    return {
        PROSPECT_FILES.account_context: _source_artifact(crm, source="crm"),
        PROSPECT_FILES.network_context: _source_artifact(network, source="network"),
        PROSPECT_FILES.freight_research: _source_artifact(freight, source="genlogs"),
        PROSPECT_FILES.company_research: _source_artifact(
            {"account_name": crm["account_name"], "signals": []}, source="company"
        ),
        PROSPECT_FILES.market_research: _source_artifact(market, source="faf"),
        PROSPECT_FILES.lane_fit_json: json.dumps(
            analysis, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
        PROSPECT_FILES.lane_fit_markdown: "\n".join(lane_lines) + "\n",
        PROSPECT_FILES.sales_brief: brief,
        PROSPECT_FILES.outreach_draft: (
            "Subject: Freight conversation\n\n"
            "Would you be open to comparing notes on your freight needs?"
        ),
    }
