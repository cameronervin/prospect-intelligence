"""Construction of the synchronous LangSmith client used by live alignment workflows."""

from langsmith import Client


def alignment_client(api_key: str) -> Client:
    """Use synchronous ingestion so publication errors are immediate and attributable."""

    if not api_key.strip():
        raise ValueError("LangSmith API key must be non-empty")
    return Client(api_key=api_key, auto_batch_tracing=False)


__all__ = ["alignment_client"]
