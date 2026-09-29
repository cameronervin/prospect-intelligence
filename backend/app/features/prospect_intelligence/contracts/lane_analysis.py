"""Strict wire contract for the versioned lane-analysis artifact."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Self, cast

from ..domain.models import LaneFitResult
from .models import FitVerdict

_LANE_ANALYSIS_METHOD_VERSION = "lane_fit_v1"
_LANE_ANALYSIS_FIELDS = frozenset({"method_version", "verdict", "top_lanes"})
_LANE_FIT_FIELDS = frozenset(
    {
        "origin",
        "destination",
        "shipper_loads_per_week",
        "matched_loads_per_week",
        "backhaul_fill",
        "density",
        "equipment_match",
        "fit_score",
        "modeled_annual_revenue",
        "deadhead_miles_avoided",
        "method_version",
    }
)


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def _require_exact_fields(
    value: Mapping[object, object], expected: frozenset[str], label: str
) -> None:
    actual = {key for key in value if isinstance(key, str)}
    expected_fields = set(expected)
    if len(actual) != len(value) or actual != expected_fields:
        missing = sorted(expected_fields.difference(actual))
        extra = sorted(str(item) for item in value if item not in expected_fields)
        raise ValueError(f"{label} fields must be exact; missing={missing}, extra={extra}")


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _require_decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{field_name} must be a decimal string") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field_name} must be a finite non-negative decimal")
    return parsed


def _lane_fit_from_payload(value: object) -> LaneFitResult:
    if not isinstance(value, Mapping):
        raise ValueError("lane score must be a JSON object")
    payload = cast("Mapping[object, object]", value)
    _require_exact_fields(payload, _LANE_FIT_FIELDS, "lane score")
    return LaneFitResult(
        origin=_require_text(payload["origin"], "origin"),
        destination=_require_text(payload["destination"], "destination"),
        shipper_loads_per_week=_require_integer(
            payload["shipper_loads_per_week"], "shipper_loads_per_week"
        ),
        matched_loads_per_week=_require_integer(
            payload["matched_loads_per_week"], "matched_loads_per_week"
        ),
        backhaul_fill=_require_decimal(payload["backhaul_fill"], "backhaul_fill"),
        density=_require_decimal(payload["density"], "density"),
        equipment_match=_require_decimal(payload["equipment_match"], "equipment_match"),
        fit_score=_require_decimal(payload["fit_score"], "fit_score"),
        modeled_annual_revenue=_require_decimal(
            payload["modeled_annual_revenue"], "modeled_annual_revenue"
        ),
        deadhead_miles_avoided=_require_integer(
            payload["deadhead_miles_avoided"], "deadhead_miles_avoided"
        ),
        method_version=_require_text(payload["method_version"], "lane method_version"),
    )


def _lane_fit_payload(lane: LaneFitResult) -> dict[str, object]:
    return {
        "origin": lane.origin,
        "destination": lane.destination,
        "shipper_loads_per_week": lane.shipper_loads_per_week,
        "matched_loads_per_week": lane.matched_loads_per_week,
        "backhaul_fill": str(lane.backhaul_fill),
        "density": str(lane.density),
        "equipment_match": str(lane.equipment_match),
        "fit_score": str(lane.fit_score),
        "modeled_annual_revenue": str(lane.modeled_annual_revenue),
        "deadhead_miles_avoided": lane.deadhead_miles_avoided,
        "method_version": lane.method_version,
    }


@dataclass(frozen=True, slots=True)
class LaneAnalysisArtifact:
    """Canonical structured output of the deterministic lane-analysis stage."""

    method_version: str
    verdict: FitVerdict
    top_lanes: tuple[LaneFitResult, ...]

    def __post_init__(self) -> None:
        if self.method_version != _LANE_ANALYSIS_METHOD_VERSION:
            raise ValueError("lane analysis must declare method_version lane_fit_v1")
        if not isinstance(cast(object, self.verdict), FitVerdict):
            raise ValueError("lane analysis verdict must be a FitVerdict")
        if len(self.top_lanes) > 3:
            raise ValueError("lane analysis may contain at most three top lanes")
        if self.verdict is FitVerdict.FIT and not self.top_lanes:
            raise ValueError("fit verdict requires at least one top lane")
        if self.verdict is not FitVerdict.FIT and self.top_lanes:
            raise ValueError("non-fit verdicts cannot contain top lanes")

        keys: set[tuple[str, str]] = set()
        for lane_value in cast("tuple[object, ...]", self.top_lanes):
            if not isinstance(lane_value, LaneFitResult):
                raise ValueError("top_lanes must contain LaneFitResult records")
            lane = lane_value
            if lane.method_version != self.method_version:
                raise ValueError("lane score method_version must match the artifact")
            key = (lane.origin, lane.destination)
            if key in keys:
                raise ValueError(f"duplicate top lane: {lane.origin}-{lane.destination}")
            keys.add(key)

        ranked = tuple(
            sorted(
                self.top_lanes,
                key=lambda lane: (
                    -lane.fit_score,
                    -lane.matched_loads_per_week,
                    lane.origin,
                    lane.destination,
                ),
            )
        )
        if ranked != self.top_lanes:
            raise ValueError("top lanes must use the canonical rank order")

    @classmethod
    def from_json(cls, raw: str) -> Self:
        """Parse a fail-closed JSON artifact without accepting unknown or partial fields."""

        try:
            value = cast(object, json.loads(raw, object_pairs_hook=_strict_json_object))
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("lane analysis must contain valid JSON") from error
        if not isinstance(value, Mapping):
            raise ValueError("lane analysis must be a JSON object")
        payload = cast("Mapping[object, object]", value)
        _require_exact_fields(payload, _LANE_ANALYSIS_FIELDS, "lane analysis artifact")
        method_version = _require_text(payload["method_version"], "method_version")
        verdict_value = _require_text(payload["verdict"], "verdict")
        try:
            verdict = FitVerdict(verdict_value)
        except ValueError as error:
            raise ValueError("lane analysis verdict is invalid") from error
        raw_lanes = payload["top_lanes"]
        if not isinstance(raw_lanes, list):
            raise ValueError("top_lanes must be a JSON array")
        return cls(
            method_version=method_version,
            verdict=verdict,
            top_lanes=tuple(
                _lane_fit_from_payload(lane) for lane in cast("list[object]", raw_lanes)
            ),
        )

    def to_json(self) -> str:
        """Serialize the canonical JSON form without lossy floating-point conversion."""

        return json.dumps(
            {
                "method_version": self.method_version,
                "verdict": self.verdict.value,
                "top_lanes": [_lane_fit_payload(lane) for lane in self.top_lanes],
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
