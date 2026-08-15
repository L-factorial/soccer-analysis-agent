from collections.abc import Iterable

from app.domain import GameState, PlayerState, Vector2
from app.spatial.errors import UnknownPlayerError
from app.spatial.vector import distance


def players_sorted_by_distance(
    players: Iterable[PlayerState],
    position: Vector2,
) -> tuple[PlayerState, ...]:
    return tuple(sorted(players, key=lambda player: (distance(player.position, position), player.id)))


def nearest_player(
    state: GameState,
    position: Vector2,
    exclude_player_id: str | None = None,
) -> PlayerState | None:
    candidates = (
        player
        for player in state.players_by_id.values()
        if player.id != exclude_player_id
    )
    return next(iter(players_sorted_by_distance(candidates, position)), None)


def teammates(state: GameState, player_id: str) -> tuple[PlayerState, ...]:
    player = _player(state, player_id)
    return tuple(
        state.players_by_id[teammate_id]
        for teammate_id in state.player_ids_by_team[player.team_id]
        if teammate_id != player_id
    )


def opponents(state: GameState, player_id: str) -> tuple[PlayerState, ...]:
    player = _player(state, player_id)
    return tuple(
        candidate
        for candidate in state.players_by_id.values()
        if candidate.team_id != player.team_id
    )


def nearest_teammate(state: GameState, player_id: str) -> PlayerState | None:
    player = _player(state, player_id)
    return next(iter(players_sorted_by_distance(teammates(state, player_id), player.position)), None)


def nearest_opponent(state: GameState, player_id: str) -> PlayerState | None:
    player = _player(state, player_id)
    return next(iter(players_sorted_by_distance(opponents(state, player_id), player.position)), None)


def players_within_radius(
    state: GameState,
    position: Vector2,
    radius: float,
) -> tuple[PlayerState, ...]:
    if radius < 0:
        raise ValueError("Radius cannot be negative")
    candidates = (
        player
        for player in state.players_by_id.values()
        if distance(player.position, position) <= radius
    )
    return players_sorted_by_distance(candidates, position)


def _player(state: GameState, player_id: str) -> PlayerState:
    player = state.players_by_id.get(player_id)
    if player is None:
        raise UnknownPlayerError(f"Unknown player: {player_id}")
    return player
