"""Freight-intelligence source adapters."""

from .genlogs import GenLogsFreightIntelligenceSource
from .synthetic import SyntheticFreightIntelligenceSource

__all__ = ["GenLogsFreightIntelligenceSource", "SyntheticFreightIntelligenceSource"]
