"""Compatibility imports for the relocated game-engine instruction adapter.

New code should import these names from :mod:`app.game_engine`. This module is
kept so existing integrations and tests do not break during the refactor.
"""

from app.game_engine.instructions import (
    TacticalInstructionPolicy,
    interpret_tactical_instruction,
)

__all__ = ["TacticalInstructionPolicy", "interpret_tactical_instruction"]
