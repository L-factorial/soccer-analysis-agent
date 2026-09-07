"""Ball-centered numerical matchups, independent of planning and presentation."""

from dataclasses import dataclass
from math import isfinite

from app.domain import AttackingDirection, GameState, PossessionStatus, Vector2, is_goalkeeper
from app.spatial import distance
from app.analysis.passing import PassPolicy, analyze_pass_to_player
from app.analysis.passing_triangles import PassingTriangle, PassingTrianglePolicy, discover_passing_triangles


@dataclass(frozen=True, slots=True)
class LocalMatchupPolicy:
    radius_cm: float = 1000
    minimum_support_spacing_cm: float = 300
    attacking_progress_start: float = 0.5
    triangles: PassingTrianglePolicy = PassingTrianglePolicy()

    def __post_init__(self) -> None:
        if not isfinite(self.radius_cm) or self.radius_cm <= 0:
            raise ValueError("Matchup radius must be finite and positive")
        if not isfinite(self.minimum_support_spacing_cm) or not 0 <= self.minimum_support_spacing_cm < self.radius_cm:
            raise ValueError("Support spacing must be nonnegative and smaller than radius")
        if not isfinite(self.attacking_progress_start) or not 0 <= self.attacking_progress_start < 1:
            raise ValueError("Attacking progress start must be in [0, 1)")


@dataclass(frozen=True, slots=True)
class LocalMatchup:
    team_id: str
    carrier_id: str
    center: Vector2
    radius: float
    attacker_ids: tuple[str, ...]
    defender_ids: tuple[str, ...]
    goalkeeper_ids: tuple[str, ...]
    usable_support_ids: tuple[str, ...]
    attacking_value: float
    numerical_value: float
    triangles: tuple[PassingTriangle, ...] = ()

    @property
    def triangle_value(self) -> float:
        return self.attacking_value * max((triangle.quality for triangle in self.triangles), default=0)

    @property
    def scenario(self) -> str:
        return f"{len(self.attacker_ids)}v{len(self.defender_ids)}"

    @property
    def value(self) -> float:
        return self.attacking_value * self.numerical_value


def discover_local_matchup(
    state: GameState,
    policy: LocalMatchupPolicy = LocalMatchupPolicy(),
    pass_policy: PassPolicy = PassPolicy(),
) -> LocalMatchup | None:
    """Measure one local contest at a controlled-possession phase boundary.

    Counts are geometric and include the circle boundary. Scoring counts only
    spaced, onside support with a feasible pass; all opponents still participate
    in the existing pass-interception checks, even outside the circle.
    """
    if state.scored_goal_id is not None or state.possession.status != PossessionStatus.CONTROLLED:
        return None
    carrier = state.players_by_id[state.possession.player_id]
    if is_goalkeeper(carrier):
        return None
    team = state.teams_by_id[carrier.team_id]
    center = carrier.position
    nearby = sorted(
        (p for p in state.players_by_id.values() if distance(center, p.position) <= policy.radius_cm),
        key=lambda p: p.id,
    )
    attackers = tuple(p for p in nearby if p.team_id == team.id and not is_goalkeeper(p))
    defenders = tuple(p for p in nearby if p.team_id != team.id and not is_goalkeeper(p))
    keepers = tuple(p.id for p in nearby if p.team_id != team.id and is_goalkeeper(p))

    def progress(point: Vector2) -> float:
        return point.x if team.attacking_direction == AttackingDirection.POSITIVE_X else state.field.length - point.x

    opponent_progress = sorted(
        (progress(p.position) for p in state.players_by_id.values() if p.team_id != team.id),
        reverse=True,
    )
    offside_line = max(progress(state.ball.position), opponent_progress[1] if len(opponent_progress) >= 2 else 0)
    support = []
    for attacker in attackers:
        if attacker.id == carrier.id:
            continue
        if progress(attacker.position) > max(state.field.length / 2, offside_line) + 1:
            continue
        if any(distance(attacker.position, p.position) < policy.minimum_support_spacing_cm for p in (carrier, *support)):
            continue
        if analyze_pass_to_player(state, carrier.id, attacker.id, policy=pass_policy).feasible:
            support.append(attacker)
    forward = progress(center) / state.field.length
    attacking_value = max(0, min(1, (forward - policy.attacking_progress_start) / (1 - policy.attacking_progress_start)))
    goal = state.goals_by_id[team.attacking_goal_id]
    attacking_value *= max(0, 1 - distance(center, goal.center) / state.field.length)
    numerical_value = max(-1, min(1, (1 + len(support) - len(defenders)) / (2 * max(1, len(defenders)))))
    return LocalMatchup(
        team.id, carrier.id, center, policy.radius_cm,
        tuple(p.id for p in attackers), tuple(p.id for p in defenders), keepers,
        tuple(p.id for p in support), attacking_value, numerical_value,
        discover_passing_triangles(state, carrier.id, tuple(p.id for p in support), pass_policy, policy.triangles),
    )
