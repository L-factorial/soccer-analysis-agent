"""Authoritative entry point for deterministic tactical decision rules."""

from app.phases.scoring import PhaseScoringPolicy, score_phase_result
from app.phases.templates import PhaseGenerationPolicy, generate_tactical_phases

__all__ = [
    "PhaseGenerationPolicy",
    "PhaseScoringPolicy",
    "generate_tactical_phases",
    "score_phase_result",
]
