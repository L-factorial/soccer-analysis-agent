from app.agent.models import TacticalObservation
from app.domain import AttackingDirection, TargetZoneSource
from app.planning import AnalyzedGameState
from app.spatial import distance


def _field_third(normalized_x: float) -> str:
    if normalized_x < 1 / 3:
        return "DEFENSIVE"
    if normalized_x < 2 / 3:
        return "MIDDLE"
    return "ATTACKING"


def _lateral_channel(
    y: float,
    field_width: float,
    direction: AttackingDirection,
) -> str:
    normalized_y = y / field_width
    if 1 / 3 <= normalized_y < 2 / 3:
        return "CENTER"
    high_y_is_left = direction == AttackingDirection.POSITIVE_X
    is_left = normalized_y >= 2 / 3 if high_y_is_left else normalized_y < 1 / 3
    return "LEFT" if is_left else "RIGHT"


def _normalized_attacking_x(
    x: float,
    field_length: float,
    direction: AttackingDirection,
) -> float:
    return (
        x / field_length
        if direction == AttackingDirection.POSITIVE_X
        else (field_length - x) / field_length
    )


def build_tactical_observation(
    analyzed: AnalyzedGameState,
    instruction: str,
) -> TacticalObservation:
    """Compress engine state into soccer concepts suitable for an LLM prompt."""
    state = analyzed.game_state
    team_id = state.possession.team_id
    carrier_id = state.possession.player_id
    if team_id is None or carrier_id is None:
        raise ValueError("A tactical observation requires controlled possession")
    team = state.teams_by_id[team_id]
    players = [
        {
            "id": player.id,
            "teamId": player.team_id,
            "number": player.number,
            "x": round(player.position.x, 1),
            "y": round(player.position.y, 1),
            "speedCategory": player.speed_category.value,
            "pressure": round(analyzed.player_contexts[player.id].pressure_score, 3),
            "possessionRole": analyzed.player_contexts[player.id].possession_role.value,
        }
        for player in state.players_by_id.values()
    ]
    attackers = tuple(
        player for player in state.players_by_id.values()
        if player.team_id == team_id
    )
    defenders = tuple(
        player for player in state.players_by_id.values()
        if player.team_id != team_id
    )
    spaces = []
    for zone in state.target_zones_by_id.values():
        if zone.source == TargetZoneSource.ATTACKING_GOAL:
            continue
        if (
            zone.source == TargetZoneSource.DYNAMIC
            and zone.attacking_team_id != team_id
        ):
            continue
        nearest_attacker = min(
            attackers,
            key=lambda player: (distance(player.position, zone.center), player.id),
            default=None,
        )
        nearest_defender = min(
            defenders,
            key=lambda player: (distance(player.position, zone.center), player.id),
            default=None,
        )
        space = {
            "id": zone.id,
            "name": zone.name,
            "source": zone.source.value.upper(),
            "shape": zone.shape.value.upper(),
            "center": {
                "x": round(zone.center.x, 1),
                "y": round(zone.center.y, 1),
            },
            "lateralChannel": _lateral_channel(
                zone.center.y,
                state.field.width,
                team.attacking_direction,
            ),
            "fieldThird": _field_third(
                _normalized_attacking_x(
                    zone.center.x,
                    state.field.length,
                    team.attacking_direction,
                )
            ),
            "nearestAttackerId": (
                nearest_attacker.id if nearest_attacker is not None else None
            ),
            "nearestDefenderId": (
                nearest_defender.id if nearest_defender is not None else None
            ),
            "nearestDefenderDistanceCm": (
                round(distance(nearest_defender.position, zone.center), 1)
                if nearest_defender is not None else None
            ),
        }
        if zone.radius is not None:
            space["radius"] = round(zone.radius, 1)
        else:
            space["bottomLeft"] = {
                "x": round(zone.bottom_left.x, 1),
                "y": round(zone.bottom_left.y, 1),
            }
            space["topRight"] = {
                "x": round(zone.top_right.x, 1),
                "y": round(zone.top_right.y, 1),
            }
        spaces.append(space)
    return TacticalObservation(
        instruction=instruction,
        attackingTeamId=team_id,
        ballCarrierId=carrier_id,
        attackingDirection=team.attacking_direction.value,
        ballPosition={"x": state.ball.position.x, "y": state.ball.position.y},
        players=players,
        spaces=spaces,
        feasibleActionTypes=sorted(
            {action.action_type.value for action in analyzed.action_candidates.feasible}
        ),
    )
