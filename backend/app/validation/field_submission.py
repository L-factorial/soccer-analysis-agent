from collections import Counter
from collections.abc import Iterable

from pydantic import BaseModel

from app.models.field_submission import (
    CircularSubmittedOpenSpace,
    FieldSubmission,
    RectangularSubmittedOpenSpace,
)
from app.models.position import Position


class ValidationIssue(BaseModel):
    code: str
    path: str
    message: str


class FieldSubmissionValidationError(Exception):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        super().__init__("The submitted field configuration is invalid")
        self.issues = issues


def _duplicates(values: Iterable[object]) -> set[object]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _inside_field(position: Position, length: float, width: float) -> bool:
    return 0 <= position.x <= length and 0 <= position.y <= width


def _is_zero(position: Position, tolerance: float = 1e-9) -> bool:
    return abs(position.x) <= tolerance and abs(position.y) <= tolerance


def validate_field_submission(submission: FieldSubmission) -> None:
    """Apply deterministic domain rules to an already parsed submission.

    This function has no FastAPI, I/O, or persistence dependency. It can be
    called inline today and moved to a worker thread or task queue later.
    """
    field = submission.field_configuration
    length = field.dimensions.length
    width = field.dimensions.width
    issues: list[ValidationIssue] = []

    def add(code: str, path: str, message: str) -> None:
        issues.append(ValidationIssue(code=code, path=path, message=message))

    duplicate_team_ids = _duplicates(team.id for team in field.teams)
    for team_id in duplicate_team_ids:
        add("duplicate_team_id", "fieldConfiguration.teams", f"Duplicate team ID: {team_id}")

    duplicate_goal_ids = _duplicates(goal.id for goal in field.goals)
    for goal_id in duplicate_goal_ids:
        add("duplicate_goal_id", "fieldConfiguration.goals", f"Duplicate goal ID: {goal_id}")

    team_ids = {team.id for team in field.teams}
    goal_ids = {goal.id for goal in field.goals}
    defended_goal_ids = [team.defended_goal_id for team in field.teams]
    for index, team in enumerate(field.teams):
        if team.defended_goal_id not in goal_ids:
            add(
                "unknown_defended_goal",
                f"fieldConfiguration.teams.{index}.defendedGoalId",
                f"Team {team.id} references unknown goal {team.defended_goal_id}",
            )
    if len(set(defended_goal_ids)) != len(defended_goal_ids):
        add(
            "shared_defended_goal",
            "fieldConfiguration.teams",
            "Each team must defend a different goal",
        )

    if len({goal.side for goal in field.goals}) != len(field.goals):
        add("duplicate_goal_side", "fieldConfiguration.goals", "One goal must be on each field side")

    duplicate_player_ids = _duplicates(player.id for player in field.players)
    for player_id in duplicate_player_ids:
        add("duplicate_player_id", "fieldConfiguration.players", f"Duplicate player ID: {player_id}")

    duplicate_numbers = _duplicates(
        (player.team_id, player.number) for player in field.players
    )
    for team_id, number in duplicate_numbers:
        add(
            "duplicate_player_number",
            "fieldConfiguration.players",
            f"Team {team_id} has more than one player numbered {number}",
        )

    for index, player in enumerate(field.players):
        path = f"fieldConfiguration.players.{index}"
        if player.team_id not in team_ids:
            add("unknown_player_team", f"{path}.teamId", f"Unknown team: {player.team_id}")
        if not _inside_field(player.position, length, width):
            add("player_outside_field", f"{path}.position", f"Player {player.id} is outside the field")
        if not _is_zero(player.velocity):
            add("nonzero_initial_velocity", f"{path}.velocity", f"Player {player.id} must initially be stationary")

    if not _inside_field(field.ball.position, length, width):
        add("ball_outside_field", "fieldConfiguration.ball.position", "Ball is outside the field")
    if field.ball.speed != 0:
        add("nonzero_initial_ball_speed", "fieldConfiguration.ball.speed", "Ball must initially be stationary")

    for index, goal in enumerate(field.goals):
        path = f"fieldConfiguration.goals.{index}"
        if any(not _inside_field(point, length, width) for point in goal.coordinates):
            add("goal_outside_field", f"{path}.coordinates", f"Goal {goal.id} extends outside the field coordinates")
            continue

        x_values = {point.x for point in goal.coordinates}
        y_values = {point.y for point in goal.coordinates}
        if len(x_values) != 2 or len(y_values) != 2 or len(set((point.x, point.y) for point in goal.coordinates)) != 4:
            add("invalid_goal_rectangle", f"{path}.coordinates", f"Goal {goal.id} must contain four corners of an axis-aligned rectangle")
            continue

        goal_length = max(x_values) - min(x_values)
        goal_width = max(y_values) - min(y_values)
        if abs(goal_length - field.goal_dimensions.length) > 1e-6 or abs(goal_width - field.goal_dimensions.width) > 1e-6:
            add("goal_dimension_mismatch", f"{path}.coordinates", f"Goal {goal.id} does not match goalDimensions")
        if goal.side == "left" and min(x_values) != 0:
            add("goal_side_mismatch", path, f"Goal {goal.id} is not attached to the left boundary")
        if goal.side == "right" and max(x_values) != length:
            add("goal_side_mismatch", path, f"Goal {goal.id} is not attached to the right boundary")

    duplicate_space_ids = _duplicates(space.id for space in field.open_spaces)
    for space_id in duplicate_space_ids:
        add("duplicate_open_space_id", "fieldConfiguration.openSpaces", f"Duplicate open-space ID: {space_id}")

    for index, space in enumerate(field.open_spaces):
        path = f"fieldConfiguration.openSpaces.{index}"
        if isinstance(space, CircularSubmittedOpenSpace):
            inside = (
                space.center.x - space.radius >= 0
                and space.center.x + space.radius <= length
                and space.center.y - space.radius >= 0
                and space.center.y + space.radius <= width
            )
            if not inside:
                add("open_space_outside_field", path, f"Open space {space.id} extends outside the field")
        elif isinstance(space, RectangularSubmittedOpenSpace):
            if not (
                space.bottom_left.x < space.top_right.x
                and space.bottom_left.y < space.top_right.y
            ):
                add("invalid_open_space_rectangle", path, f"Open space {space.id} has invalid corners")
            elif not (
                _inside_field(space.bottom_left, length, width)
                and _inside_field(space.top_right, length, width)
            ):
                add("open_space_outside_field", path, f"Open space {space.id} extends outside the field")

    if issues:
        raise FieldSubmissionValidationError(issues)
