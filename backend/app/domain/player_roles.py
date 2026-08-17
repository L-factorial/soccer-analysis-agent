from app.domain.game_state import PlayerState


# Version-one layouts identify goalkeepers by shirt number because the request
# schema does not yet expose an explicit player-position/role field.
GOALKEEPER_SHIRT_NUMBER = 1


def is_goalkeeper(player: PlayerState) -> bool:
    """Return whether a player has the convention-based goalkeeper role."""
    return player.number == GOALKEEPER_SHIRT_NUMBER
