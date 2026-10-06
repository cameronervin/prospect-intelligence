"""Generated artifact contract appended to every agent prompt, derived from its spec."""

from typing import TYPE_CHECKING

from ...contracts.filesystem import PROSPECT_FILES, ArtifactMediaType

if TYPE_CHECKING:
    from ..specs import AgentSpec

_F = PROSPECT_FILES


def artifact_contract(spec: "AgentSpec") -> str:
    """Describe the declared writer for every artifact without duplicating tool schemas."""

    media_types = {entry.path: entry.media_type for entry in _F.manifest_entries()}
    labels = {ArtifactMediaType.JSON: "JSON", ArtifactMediaType.MARKDOWN: "Markdown"}
    typed = {owner.path: owner.tool_name for owner in spec.artifact_tools}
    lines = [
        "Required artifacts: a text reply does not create a file. Use only the declared writer "
        "for each path:",
        *(
            f"- `{path}` ({labels[media_types[path]]}) — call `{typed[path]}`; the tool writes it"
            if path in typed
            else f"- `{path}` ({labels[media_types[path]]}) — call `write_file` with full content"
            for path in spec.required_artifacts
        ),
    ]
    if spec.writable_paths and not all(
        path.startswith(tuple(spec.readable_paths)) for path in spec.writable_paths
    ):
        lines.append("You cannot read these paths back, so write each file whole in one call.")
    return "\n".join(lines)


def artifact_reminder(spec: "AgentSpec", missing_artifacts: list[str]) -> str:
    typed = {owner.path: owner.tool_name for owner in spec.artifact_tools}
    actions = ", ".join(
        f"`{typed[path]}` for `{path}`" if path in typed else f"`write_file` for `{path}`"
        for path in missing_artifacts
    )
    return f"Required artifacts are still missing. Call {actions}; a text reply creates no file."


def render_system_prompt(spec: "AgentSpec") -> str:
    contract = artifact_contract(spec)
    correction = ""
    if spec.artifact_tools:
        correction = """

# Typed submission correction

When a typed artifact tool returns `agent_output_invalid`, use its fixed issue instructions with
the trusted run context and files. Fix every listed issue, preserve fields that are already valid,
and resubmit the same tool. Never copy rejected values from the error because error feedback does
not contain them. The third invalid submission fails the stage closed.
"""
    return (
        f"{spec.description}\n\n{spec.system_prompt}{correction}"
        f"\n\n# Required artifacts\n\n{contract}"
    )
