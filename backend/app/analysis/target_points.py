from app.domain import (
    AttackingDirection,
    GameState,
    TargetZoneShape,
    TargetZoneSource,
    TargetZoneState,
    Vector2,
)
from app.spatial import distance, nearest_point_in_zone


def _forward_point(
    zone: TargetZoneState,
    direction: AttackingDirection,
) -> Vector2:
    x = (
        zone.top_right.x
        if direction == AttackingDirection.POSITIVE_X
        else zone.bottom_left.x
    )
    return Vector2(x, zone.center.y)


def _sample_points(zone: TargetZoneState) -> tuple[Vector2, ...]:
    if zone.shape == TargetZoneShape.CIRCULAR and zone.radius is not None:
        return (
            zone.center,
            Vector2(zone.center.x + zone.radius, zone.center.y),
            Vector2(zone.center.x - zone.radius, zone.center.y),
            Vector2(zone.center.x, zone.center.y + zone.radius),
            Vector2(zone.center.x, zone.center.y - zone.radius),
        )
    return (
        zone.center,
        zone.bottom_left,
        zone.top_right,
        Vector2(zone.bottom_left.x, zone.top_right.y),
        Vector2(zone.top_right.x, zone.bottom_left.y),
    )


def tactical_target_points(
    state: GameState,
    zone: TargetZoneState,
    team_id: str,
    origin: Vector2,
) -> tuple[Vector2, ...]:
    """Return stable, distinct tactical destinations inside one open space."""
    if zone.ball_only:
        return ()
    if zone.source == TargetZoneSource.DYNAMIC:
        return (zone.center,)
    team = state.teams_by_id[team_id]
    opponents = tuple(
        player
        for player in state.players_by_id.values()
        if player.team_id != team_id
    )
    samples = _sample_points(zone)
    safest = max(
        samples,
        key=lambda point: (
            min(
                (distance(point, opponent.position) for opponent in opponents),
                default=float("inf"),
            ),
            point.x,
            point.y,
        ),
    )
    ordered = (
        nearest_point_in_zone(zone, origin),
        zone.center,
        _forward_point(zone, team.attacking_direction),
        safest,
    )
    return tuple(dict.fromkeys(ordered))
