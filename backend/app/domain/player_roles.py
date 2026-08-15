from app.domain.game_state import PlayerState


GOALKEEPER_SHIRT_NUMBER = 1


def is_goalkeeper(player: PlayerState) -> bool:
    """Return whether a player has the convention-based goalkeeper role."""
    return player.number == GOALKEEPER_SHIRT_NUMBER
