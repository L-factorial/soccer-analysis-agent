from types import MappingProxyType

from app.domain import (
    AttackingDirection,
    BallState,
    FieldState,
    GameState,
    GoalState,
    PlayerState,
    PlayerSpeedCategory,
    PossessionState,
    PossessionStatus,
    TargetZoneShape,
    TargetZoneSource,
    TargetZoneState,
    TeamState,
    Vector2,
)
from app.models.field_submission import (
    CircularSubmittedOpenSpace,
    FieldSubmission,
    RectangularSubmittedOpenSpace,
)
from app.models.goal import GoalSide
from app.models.position import Position


class GameStateBuildError(Exception):
    """Raised when validated input violates an internal builder assumption."""


def _vector(position: Position) -> Vector2:
    return Vector2(x=position.x, y=position.y)


def build_initial_game_state(submission: FieldSubmission) -> GameState:
    """Build immutable simulation state from an already validated submission."""
    submitted = submission.field_configuration

    goals_by_id: dict[str, GoalState] = {}
    for goal in submitted.goals:
        x_values = [position.x for position in goal.coordinates]
        y_values = [position.y for position in goal.coordinates]
        bottom_left = Vector2(min(x_values), min(y_values))
        top_right = Vector2(max(x_values), max(y_values))
        goals_by_id[goal.id] = GoalState(
            id=goal.id,
            name=goal.name,
            side=goal.side,
            coordinates=tuple(_vector(position) for position in goal.coordinates),
            center=Vector2(
                x=(bottom_left.x + top_right.x) / 2,
                y=(bottom_left.y + top_right.y) / 2,
            ),
            bottom_left=bottom_left,
            top_right=top_right,
        )

    teams_by_id: dict[str, TeamState] = {}
    for team in submitted.teams:
        defended_goal = goals_by_id.get(team.defended_goal_id)
        if defended_goal is None:
            raise GameStateBuildError(
                f"Team {team.id} references missing goal {team.defended_goal_id}"
            )

        attacking_goals = [
            goal for goal in goals_by_id.values() if goal.id != defended_goal.id
        ]
        if len(attacking_goals) != 1:
            raise GameStateBuildError(
                f"Unable to derive one attacking goal for team {team.id}"
            )
        attacking_goal = attacking_goals[0]
        direction = (
            AttackingDirection.POSITIVE_X
            if attacking_goal.side == GoalSide.RIGHT
            else AttackingDirection.NEGATIVE_X
        )
        teams_by_id[team.id] = TeamState(
            id=team.id,
            name=team.name,
            color=team.color,
            defended_goal_id=defended_goal.id,
            attacking_goal_id=attacking_goal.id,
            attacking_direction=direction,
        )

    players_by_id: dict[str, PlayerState] = {}
    player_ids_by_team: dict[str, list[str]] = {
        team_id: [] for team_id in teams_by_id
    }
    for player in submitted.players:
        if player.team_id not in teams_by_id:
            raise GameStateBuildError(
                f"Player {player.id} references missing team {player.team_id}"
            )
        players_by_id[player.id] = PlayerState(
            id=player.id,
            name=player.name,
            number=player.number,
            team_id=player.team_id,
            position=_vector(player.position),
            orientation=player.orientation,
            velocity=_vector(player.velocity),
            speed_category=PlayerSpeedCategory(player.speed_category),
        )
        player_ids_by_team[player.team_id].append(player.id)

    target_zones_by_id: dict[str, TargetZoneState] = {}
    for space in submitted.open_spaces:
        if isinstance(space, CircularSubmittedOpenSpace):
            center = _vector(space.center)
            target_zones_by_id[space.id] = TargetZoneState(
                id=space.id,
                name=space.name,
                shape=TargetZoneShape.CIRCULAR,
                source=TargetZoneSource.USER_DEFINED,
                center=center,
                bottom_left=Vector2(
                    center.x - space.radius,
                    center.y - space.radius,
                ),
                top_right=Vector2(
                    center.x + space.radius,
                    center.y + space.radius,
                ),
                radius=space.radius,
            )
        elif isinstance(space, RectangularSubmittedOpenSpace):
            bottom_left = _vector(space.bottom_left)
            top_right = _vector(space.top_right)
            target_zones_by_id[space.id] = TargetZoneState(
                id=space.id,
                name=space.name,
                shape=TargetZoneShape.RECTANGULAR,
                source=TargetZoneSource.USER_DEFINED,
                center=Vector2(
                    x=(bottom_left.x + top_right.x) / 2,
                    y=(bottom_left.y + top_right.y) / 2,
                ),
                bottom_left=bottom_left,
                top_right=top_right,
            )
        else:
            raise GameStateBuildError(
                f"Unsupported target-zone type for {space.id}"
            )

    for team in teams_by_id.values():
        goal = goals_by_id[team.attacking_goal_id]
        zone_id = f"GoalSpace-{team.id}"
        target_zones_by_id[zone_id] = TargetZoneState(
            id=zone_id,
            name=goal.name,
            shape=TargetZoneShape.RECTANGULAR,
            source=TargetZoneSource.ATTACKING_GOAL,
            center=goal.center,
            bottom_left=goal.bottom_left,
            top_right=goal.top_right,
            attacking_team_id=team.id,
            ball_only=True,
        )

    return GameState(
        time_seconds=0,
        field=FieldState(
            field_type=submitted.field_type,
            length=submitted.dimensions.length,
            width=submitted.dimensions.width,
            unit=submitted.dimensions.unit,
        ),
        teams_by_id=MappingProxyType(teams_by_id),
        goals_by_id=MappingProxyType(goals_by_id),
        players_by_id=MappingProxyType(players_by_id),
        player_ids_by_team=MappingProxyType(
            {
                team_id: tuple(player_ids)
                for team_id, player_ids in player_ids_by_team.items()
            }
        ),
        ball=BallState(
            position=_vector(submitted.ball.position),
            direction=submitted.ball.direction,
            speed=submitted.ball.speed,
            velocity=Vector2(0, 0),
        ),
        target_zones_by_id=MappingProxyType(target_zones_by_id),
        possession=PossessionState(
            status=PossessionStatus.UNRESOLVED,
            player_id=None,
            team_id=None,
            contesting_player_ids=(),
        ),
    )
