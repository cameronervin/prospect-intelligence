"""Topology kept separate from runtime compilation and node implementations."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProspectGraphBlueprint:
    entrypoint: str
    parallel_stage: tuple[str, ...]
    sequential_stage: tuple[str, ...]
    review_boundary: str
    terminal_stage: str


def create_prospect_graph_blueprint() -> ProspectGraphBlueprint:
    return ProspectGraphBlueprint(
        entrypoint="prepare_run",
        parallel_stage=("account-context", "external-research"),
        sequential_stage=("lane-analyst", "outreach-drafter"),
        review_boundary="review_outreach",
        terminal_stage="record_completion",
    )
