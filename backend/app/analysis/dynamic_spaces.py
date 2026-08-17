from dataclasses import dataclass, replace
from types import MappingProxyType

from app.domain import (
    AttackingDirection,
    GameState,
    TargetZoneShape,
    TargetZoneSource,
    TargetZoneState,
    Vector2,
)
from app.spatial import distance


@dataclass(frozen=True, slots=True)
class DynamicSpacePolicy:
    """Sampling and clearance bounds for engine-generated open spaces."""
    maximum_spaces_per_team: int = 3
    minimum_defender_clearance_cm: float = 700
    minimum_separation_cm: float = 1400
    minimum_radius_cm: float = 300
    maximum_radius_cm: float = 800
    maximum_attacker_distance_cm: float = 4500


def discover_dynamic_open_spaces(
    state: GameState,
    team_id: str,
    policy: DynamicSpacePolicy = DynamicSpacePolicy(),
) -> tuple[TargetZoneState, ...]:
    """Find a small deterministic set of useful unoccupied field regions."""
    team = state.teams_by_id[team_id]
    opponents = tuple(
        player for player in state.players_by_id.values()
        if player.team_id != team_id
    )
    teammates = tuple(
        state.players_by_id[player_id]
        for player_id in state.player_ids_by_team[team_id]
    )
    x_fractions = (0.25, 0.375, 0.5, 0.625, 0.75, 0.875)
    y_fractions = (0.12, 0.31, 0.5, 0.69, 0.88)
    candidates: list[tuple[float, Vector2, float]] = []

    for x_fraction in x_fractions:
        for y_fraction in y_fractions:
            point = Vector2(
                state.field.length * x_fraction,
                state.field.width * y_fraction,
            )
            defender_clearance = min(
                (distance(point, player.position) for player in opponents),
                default=state.field.width,
            )
            teammate_clearance = min(
                (distance(point, player.position) for player in teammates),
                default=state.field.width,
            )
            if defender_clearance < policy.minimum_defender_clearance_cm:
                continue
            if teammate_clearance < policy.minimum_radius_cm:
                continue
            if teammate_clearance > policy.maximum_attacker_distance_cm:
                continue
            forward_value = (
                x_fraction
                if team.attacking_direction == AttackingDirection.POSITIVE_X
                else 1 - x_fraction
            )
            ball_distance = distance(point, state.ball.position)
            reachability = max(0, 1 - ball_distance / state.field.length)
            attacker_reachability = max(
                0,
                1 - teammate_clearance / policy.maximum_attacker_distance_cm,
            )
            score = (
                defender_clearance / state.field.width
                + 0.55 * forward_value
                + 0.35 * reachability
                + 0.8 * attacker_reachability
            )
            radius = min(
                policy.maximum_radius_cm,
                max(policy.minimum_radius_cm, defender_clearance * 0.35),
            )
            candidates.append((score, point, radius))

    ranked = sorted(
        candidates,
        key=lambda item: (-item[0], -item[1].x, item[1].y),
    )
    selected: list[tuple[float, Vector2, float]] = []

    def add_if_separated(candidate: tuple[float, Vector2, float]) -> None:
        if any(
            distance(candidate[1], existing[1]) < policy.minimum_separation_cm
            for existing in selected
        ):
            return
        selected.append(candidate)

    if ranked:
        add_if_separated(ranked[0])
        forward_order = sorted(
            ranked,
            key=lambda item: (
                -item[1].x
                if team.attacking_direction == AttackingDirection.POSITIVE_X
                else item[1].x,
                -item[0],
                item[1].y,
            ),
        )
        for candidate in forward_order:
            before = len(selected)
            add_if_separated(candidate)
            if len(selected) > before:
                break

    for candidate in ranked:
        add_if_separated(candidate)
        if len(selected) == policy.maximum_spaces_per_team:
            break

    return tuple(
        TargetZoneState(
            id=f"DynamicSpace-{team_id}-{index}",
            name=f"DynamicSpace-{team_id}-{index}",
            shape=TargetZoneShape.CIRCULAR,
            source=TargetZoneSource.DYNAMIC,
            center=point,
            bottom_left=Vector2(point.x - radius, point.y - radius),
            top_right=Vector2(point.x + radius, point.y + radius),
            radius=radius,
            attacking_team_id=team_id,
        )
        for index, (_, point, radius) in enumerate(selected, start=1)
    )


def with_dynamic_open_spaces(
    state: GameState,
    policy: DynamicSpacePolicy = DynamicSpacePolicy(),
) -> GameState:
    static_zones = {
        zone_id: zone
        for zone_id, zone in state.target_zones_by_id.items()
        if zone.source != TargetZoneSource.DYNAMIC
    }
    team_ids = (
        (state.possession.team_id,)
        if state.possession.team_id is not None
        else tuple(sorted(state.teams_by_id))
    )
    for team_id in team_ids:
        for zone in discover_dynamic_open_spaces(state, team_id, policy):
            static_zones[zone.id] = zone
    return replace(state, target_zones_by_id=MappingProxyType(static_zones))
