"""Stable identifier normalization for trace and artifact names."""


def normalize_agent_name(name: str) -> str:
    return name.strip().casefold().replace("_", "-").replace(" ", "-")
