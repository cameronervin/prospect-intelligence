"""Fail-closed trace privacy defaults for every LangChain/LangSmith child run."""

import os


def configure_trace_privacy() -> None:
    """Keep model, tool, and scope metadata out of traces."""

    os.environ["LANGSMITH_HIDE_INPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_METADATA"] = "true"
