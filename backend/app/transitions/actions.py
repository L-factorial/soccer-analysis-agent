from dataclasses import dataclass, replace
from types import MappingProxyType

from app.analysis import ActionCandidate, ActionType, game_state_fingerprint
from app.domain import (
    BallState,
    GameState,
    PlayerState,
    PossessionState,
    PossessionStatus,
    Vector2,
)
from app.spatial import distance, move_toward, orientation_degrees


class InvalidActionTransitionError(ValueError):
    """Base error for an action that cannot be applied to a game state."""


class InfeasibleActionError(InvalidActionTransitionError):
    """Raised when a rejected action candidate is applied."""


class StaleActionCandidateError(InvalidActionTransitionError):
    """Raised when a candidate was generated from a different game state."""


class InvalidTransitionPolicyError(ValueError):
    """Raised when transition reaction settings are invalid."""


@dataclass(frozen=True, slots=True)
class TransitionPolicy:
    defender_reaction_speed_cm_per_second: float = 500
    enable_defender_reaction: bool = True

    def __post_init__(self) -> None:
        if self.defender_reaction_speed_cm_per_second <= 0:
            raise InvalidTransitionPolicyError(
                "Defender reaction speed must be positive"
            )


@dataclass(frozen=True, slots=True)
class ActionTransition:
    candidate_id: str
    previous_time_seconds: float
    resulting_time_seconds: float
    previous_state: GameState
    resulting_state: GameState
    changed_player_ids: tuple[str, ...]
    ball_changed: bool
    possession_changed: bool


def _stationary_player(
    player: PlayerState,
    position: Vector2,
    orientation: float,
) -> PlayerState:
    return replace(
        player,
        position=position,
        orientation=orientation,
        velocity=Vector2(0, 0),
    )


def _stationary_ball(position: Vector2, direction: float) -> BallState:
    return BallState(
        position=position,
        direction=direction,
        speed=0,
        velocity=Vector2(0, 0),
    )


def _controlled_possession(state: GameState, player_id: str) -> PossessionState:
    return PossessionState(
        status=PossessionStatus.CONTROLLED,
        player_id=player_id,
        team_id=state.players_by_id[player_id].team_id,
    )


def _updated_players(
    state: GameState,
    updates: dict[str, PlayerState],
) -> MappingProxyType:
    players = dict(state.players_by_id)
    players.update(updates)
    return MappingProxyType(players)


def apply_action_candidate(
    state: GameState,
    candidate: ActionCandidate,
    policy: TransitionPolicy = TransitionPolicy(),
) -> ActionTransition:
    """Apply one feasible candidate and return a new immutable branch state."""
    if not candidate.feasible:
        raise InfeasibleActionError(
            f"Candidate {candidate.id} is infeasible: {', '.join(candidate.issue_codes)}"
        )
    if candidate.originating_state_fingerprint != game_state_fingerprint(state):
        raise StaleActionCandidateError(
            f"Candidate {candidate.id} was generated from a different game state"
        )
    if candidate.actor_id not in state.players_by_id:
        raise InvalidActionTransitionError(
            f"Unknown action actor: {candidate.actor_id}"
        )

    player_updates: dict[str, PlayerState] = {}
    ball = state.ball
    possession = state.possession
    scored_goal_id = state.scored_goal_id
    scoring_team_id = state.scoring_team_id
    changed_players: tuple[str, ...] = ()

    if candidate.action_type in {
        ActionType.MOVE,
        ActionType.RUN,
        ActionType.MOVE_WITH_BALL,
    }:
        actor = state.players_by_id[candidate.actor_id]
        moved_actor = _stationary_player(
            actor,
            candidate.destination,
            candidate.source_analysis.orientation_degrees,
        )
        player_updates[actor.id] = moved_actor
        if candidate.action_type == ActionType.MOVE_WITH_BALL:
            ball = _stationary_ball(
                candidate.destination,
                candidate.source_analysis.orientation_degrees,
            )
            possession = _controlled_possession(state, actor.id)

    elif candidate.action_type in {
        ActionType.PASS_TO_PLAYER,
        ActionType.PASS_TO_SPACE,
    }:
        if candidate.receiver_id is None:
            raise InvalidActionTransitionError("Pass candidate has no receiver")
        receiver = state.players_by_id.get(candidate.receiver_id)
        if receiver is None:
            raise InvalidActionTransitionError(
                f"Unknown pass receiver: {candidate.receiver_id}"
            )
        ball = _stationary_ball(
            candidate.destination,
            candidate.source_analysis.orientation_degrees,
        )
        possession = _controlled_possession(state, receiver.id)
        if candidate.action_type == ActionType.PASS_TO_SPACE:
            moved_receiver = _stationary_player(
                receiver,
                candidate.destination,
                receiver.orientation,
            )
            player_updates[receiver.id] = moved_receiver
    elif candidate.action_type == ActionType.SHOT:
        actor = state.players_by_id[candidate.actor_id]
        ball = _stationary_ball(
            candidate.destination,
            candidate.source_analysis.orientation_degrees,
        )
        possession = PossessionState(
            status=PossessionStatus.LOOSE,
            player_id=None,
            team_id=None,
        )
        scored_goal_id = candidate.source_analysis.goal_id
        scoring_team_id = actor.team_id
    else:
        raise InvalidActionTransitionError(
            f"Unsupported action type: {candidate.action_type}"
        )

    if policy.enable_defender_reaction:
        actor_team_id = state.players_by_id[candidate.actor_id].team_id
        defenders = tuple(
            player
            for player in state.players_by_id.values()
            if player.team_id != actor_team_id
        )
        defender = min(
            defenders,
            key=lambda player: (
                distance(player.position, candidate.destination),
                player.id,
            ),
            default=None,
        )
        if defender is not None:
            destination = move_toward(
                defender.position,
                candidate.destination,
                policy.defender_reaction_speed_cm_per_second
                * (
                    candidate.metrics.ball_travel_duration_seconds
                    or candidate.metrics.duration_seconds
                ),
            )
            if destination != defender.position:
                player_updates[defender.id] = _stationary_player(
                    defender,
                    destination,
                    orientation_degrees(
                        defender.position,
                        candidate.destination,
                    ),
                )

    players = (
        _updated_players(state, player_updates)
        if player_updates
        else state.players_by_id
    )
    changed_players = tuple(player_updates)
    resulting_state = replace(
        state,
        time_seconds=state.time_seconds + candidate.metrics.duration_seconds,
        players_by_id=players,
        ball=ball,
        possession=possession,
        scored_goal_id=scored_goal_id,
        scoring_team_id=scoring_team_id,
    )
    return ActionTransition(
        candidate_id=candidate.id,
        previous_time_seconds=state.time_seconds,
        resulting_time_seconds=resulting_state.time_seconds,
        previous_state=state,
        resulting_state=resulting_state,
        changed_player_ids=changed_players,
        ball_changed=ball != state.ball,
        possession_changed=possession != state.possession,
    )
