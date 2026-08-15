from dataclasses import dataclass, replace
from enum import StrEnum

from app.domain import GameState, PossessionState, PossessionStatus
from app.spatial import distance, players_sorted_by_distance


class InvalidPossessionPolicyError(ValueError):
    """Raised when possession thresholds are internally inconsistent."""


@dataclass(frozen=True, slots=True)
class PossessionPolicy:
    control_radius_cm: float = 100
    contested_radius_cm: float = 150
    ambiguity_distance_cm: float = 30
    stationary_ball_speed_threshold: float = 10

    def __post_init__(self) -> None:
        if self.control_radius_cm < 0:
            raise InvalidPossessionPolicyError("Control radius cannot be negative")
        if self.contested_radius_cm < self.control_radius_cm:
            raise InvalidPossessionPolicyError(
                "Contested radius cannot be smaller than control radius"
            )
        if self.ambiguity_distance_cm < 0:
            raise InvalidPossessionPolicyError(
                "Ambiguity distance cannot be negative"
            )
        if self.stationary_ball_speed_threshold < 0:
            raise InvalidPossessionPolicyError(
                "Stationary-ball speed threshold cannot be negative"
            )


class PossessionReason(StrEnum):
    CLEAR_CONTROL = "clear_control"
    NO_PLAYERS = "no_players"
    OUTSIDE_CONTROL_RADIUS = "outside_control_radius"
    OPPONENT_WITHIN_AMBIGUITY_RANGE = "opponent_within_ambiguity_range"
    BALL_IN_MOTION = "ball_in_motion"


@dataclass(frozen=True, slots=True)
class PossessionAnalysis:
    possession: PossessionState
    reason: PossessionReason
    nearest_player_id: str | None
    nearest_player_distance_cm: float | None
    nearest_opponent_id: str | None
    nearest_opponent_distance_cm: float | None


def _loose_analysis(
    reason: PossessionReason,
    nearest_player_id: str | None = None,
    nearest_player_distance_cm: float | None = None,
) -> PossessionAnalysis:
    return PossessionAnalysis(
        possession=PossessionState(
            status=PossessionStatus.LOOSE,
            player_id=None,
            team_id=None,
        ),
        reason=reason,
        nearest_player_id=nearest_player_id,
        nearest_player_distance_cm=nearest_player_distance_cm,
        nearest_opponent_id=None,
        nearest_opponent_distance_cm=None,
    )


def analyze_initial_possession(
    state: GameState,
    policy: PossessionPolicy = PossessionPolicy(),
) -> PossessionAnalysis:
    """Resolve possession from player/ball distance in a static field state.

    TODO: Consider player orientation and a control cone when orientation becomes
    a reliable editor or tracking input.
    """
    ordered_players = players_sorted_by_distance(
        state.players_by_id.values(),
        state.ball.position,
    )
    if not ordered_players:
        return _loose_analysis(PossessionReason.NO_PLAYERS)

    nearest = ordered_players[0]
    nearest_distance = distance(nearest.position, state.ball.position)
    if state.ball.speed > policy.stationary_ball_speed_threshold:
        return _loose_analysis(
            PossessionReason.BALL_IN_MOTION,
            nearest.id,
            nearest_distance,
        )
    if nearest_distance > policy.control_radius_cm:
        return _loose_analysis(
            PossessionReason.OUTSIDE_CONTROL_RADIUS,
            nearest.id,
            nearest_distance,
        )

    ordered_opponents = tuple(
        player
        for player in ordered_players
        if player.team_id != nearest.team_id
    )
    nearest_opponent = ordered_opponents[0] if ordered_opponents else None
    nearest_opponent_distance = (
        distance(nearest_opponent.position, state.ball.position)
        if nearest_opponent
        else None
    )
    contesting_opponents = tuple(
        player
        for player in ordered_opponents
        if distance(player.position, state.ball.position)
        <= policy.contested_radius_cm
        and abs(distance(player.position, state.ball.position) - nearest_distance)
        <= policy.ambiguity_distance_cm
    )

    if contesting_opponents:
        return PossessionAnalysis(
            possession=PossessionState(
                status=PossessionStatus.CONTESTED,
                player_id=None,
                team_id=None,
                contesting_player_ids=(
                    nearest.id,
                    *(player.id for player in contesting_opponents),
                ),
            ),
            reason=PossessionReason.OPPONENT_WITHIN_AMBIGUITY_RANGE,
            nearest_player_id=nearest.id,
            nearest_player_distance_cm=nearest_distance,
            nearest_opponent_id=nearest_opponent.id if nearest_opponent else None,
            nearest_opponent_distance_cm=nearest_opponent_distance,
        )

    return PossessionAnalysis(
        possession=PossessionState(
            status=PossessionStatus.CONTROLLED,
            player_id=nearest.id,
            team_id=nearest.team_id,
        ),
        reason=PossessionReason.CLEAR_CONTROL,
        nearest_player_id=nearest.id,
        nearest_player_distance_cm=nearest_distance,
        nearest_opponent_id=nearest_opponent.id if nearest_opponent else None,
        nearest_opponent_distance_cm=nearest_opponent_distance,
    )


def apply_possession_analysis(
    state: GameState,
    analysis: PossessionAnalysis,
) -> GameState:
    return replace(state, possession=analysis.possession)


def resolve_initial_possession(
    state: GameState,
    policy: PossessionPolicy = PossessionPolicy(),
) -> tuple[GameState, PossessionAnalysis]:
    analysis = analyze_initial_possession(state, policy)
    return apply_possession_analysis(state, analysis), analysis
