"""SDK-neutral contracts shared by offline targets and evaluators."""

from evaluation.contracts.snapshot import OfflineRunSnapshot, normalize_snapshot

__all__ = ["OfflineRunSnapshot", "normalize_snapshot"]
