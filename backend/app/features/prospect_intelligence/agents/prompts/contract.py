"""Generated artifact contract appended to every agent prompt, derived from its spec."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ...contracts.filesystem import PROSPECT_FILES, ArtifactMediaType

if TYPE_CHECKING:
    from ..specs import AgentSpec

_F = PROSPECT_FILES

_SOURCE_ARTIFACT_SCHEMA = (
    "Each JSON file under /context/ or /research/ must be one JSON object containing "
    "`coverage` (an object or list stating source status, including degraded or missing "
    "coverage) and a non-empty `evidence` list. Every evidence item needs a string `claim` "
    "and a `provenance` object with non-empty `source`, `mode`, `endpoint_or_artifact`, "
    "`retrieved_at`, `evidence_location`, and `source_version`, copied from the tool result. "
    "Never invent provenance or facts that no tool returned."
)


_REVIEW_SCHEMA = (
    "The findings file must be one JSON object with exactly `round` (integer 1-3), `verdict` "
    '("pass" or "revise"), `findings` (array), and `resolved_prior` (array of prior finding ids '
    'you confirmed fixed). Each finding has exactly `id`, `file` ("brief" or "outreach"), '
    "`category` (evidence_support, lane_consistency, customer_safety, rep_preferences, "
    'structure_format, or clarity), `severity` ("blocking" or "advisory"), `excerpt`, '
    '`problem`, and `required_change`, all non-empty strings. The verdict is "pass" exactly '
    "when no finding is blocking."
)


def artifact_contract(required_artifacts: Sequence[str], readable_paths: Sequence[str]) -> str:
    """Name each file the agent must write; the framework adds no filesystem guidance."""

    media_types = {entry.path: entry.media_type for entry in _F.manifest_entries()}
    labels = {ArtifactMediaType.JSON: "JSON", ArtifactMediaType.MARKDOWN: "Markdown"}
    lines = [
        "Required artifacts: your work is complete only after you call write_file once for "
        "each path below with its full content. A text reply does not create a file.",
        *(f"- `{path}` ({labels[media_types[path]]})" for path in required_artifacts),
    ]
    if not all(path.startswith(tuple(readable_paths)) for path in required_artifacts):
        lines.append("You cannot read these paths back, so write each file whole in one call.")
    if any(path.startswith(("/context/", "/research/")) for path in required_artifacts):
        lines.append(_SOURCE_ARTIFACT_SCHEMA)
    if _F.review_findings in required_artifacts:
        lines.append(_REVIEW_SCHEMA)
    return "\n".join(lines)


def artifact_reminder(missing_artifacts: Sequence[str]) -> str:
    listed = ", ".join(f"`{path}`" for path in missing_artifacts)
    return (
        f"Your required artifacts are not written yet: {listed}. Call write_file for each "
        "missing path now; a text reply does not create a file."
    )


def render_system_prompt(spec: "AgentSpec") -> str:
    contract = artifact_contract(spec.required_artifacts, spec.readable_paths)
    return f"{spec.description}\n\n{spec.system_prompt}\n\n# Required artifacts\n\n{contract}"
