from app.analysis import ActionType, MovementPolicy, discover_dynamic_open_spaces
from app.domain import TargetZoneSource
from app.models.animation_response import (
    AnimationResponse,
    MoveEvent,
    PassEvent,
    PassToSpaceEvent,
    PlannerDiagnostics,
    ReceiveEvent,
    ShotEvent,
    TurnEvent,
)
from app.models.position import Position
from app.phases import PhaseSearchNode
from app.spatial import distance, turn_duration_seconds
# Presentation-time turning rate. Simulation already determines whether the
# phase is feasible; the scheduler uses this to place TURN before RUN/ball events.
TURNING_SPEED_DEGREES_PER_SECOND = 180


def _time(value: float) -> float:
    return round(value, 6)


def _position(x: float, y: float) -> Position:
    return Position(x=x, y=y)


def _run_pace_and_speed(
    player,
    target,
    duration: float,
    policy: MovementPolicy = MovementPolicy(),
) -> tuple[str, float]:
    """Classify the scheduled effective speed after player capability applies."""
    speed = distance(player.position, target) / duration if duration > 0 else 0
    capability_neutral_speed = speed / player.speed_category.multiplier
    regular_speed = (
        policy.slow_run_speed_cm_per_second * policy.regular_pace_multiplier
    )
    sprint_speed = regular_speed * policy.sprint_pace_multiplier
    if capability_neutral_speed <= (
        policy.slow_run_speed_cm_per_second + regular_speed
    ) / 2:
        pace = "SLOW"
    elif capability_neutral_speed <= (regular_speed + sprint_speed) / 2:
        pace = "REGULAR"
    else:
        pace = "SPRINT"
    return pace, speed


def _turn_duration(current: float, target: float) -> float:
    return turn_duration_seconds(
        current,
        target,
        TURNING_SPEED_DEGREES_PER_SECOND,
    )


def _merge_continuous_dribbles(events):
    """Join uninterrupted same-heading dribble primitives for presentation.

    Search retains bounded phases because defenders and support are recomputed
    at every boundary. When the carrier has no TURN at that boundary, however,
    two adjacent MOVE_WITH_BALL events describe one continuous physical run.
    Merging only those events removes an artificial animation seam without
    altering simulation, scoring, possession, or concurrent player events.
    """
    turn_boundaries = {
        (event.player_id, event.start_time)
        for event in events
        if isinstance(event, TurnEvent)
    }
    merged = []
    last_dribble_index_by_player = {}
    for event in sorted(events, key=lambda item: (item.start_time, item.id)):
        if isinstance(event, MoveEvent) and event.type == "MOVE_WITH_BALL":
            previous_index = last_dribble_index_by_player.get(event.player_id)
            previous = merged[previous_index] if previous_index is not None else None
            previous_end = (
                _time(previous.start_time + previous.duration)
                if isinstance(previous, MoveEvent)
                else None
            )
            if (
                isinstance(previous, MoveEvent)
                and previous.type == "MOVE_WITH_BALL"
                and previous_end == _time(event.start_time)
                and (event.player_id, event.start_time) not in turn_boundaries
                # A pace change is meaningful animation data and must remain a
                # phase boundary even when direction stays unchanged.
                and previous.pace == event.pace
            ):
                merged[previous_index] = previous.model_copy(
                    update={
                        "duration": _time(previous.duration + event.duration),
                        "target": event.target,
                    }
                )
                continue
            last_dribble_index_by_player[event.player_id] = len(merged)
        merged.append(event)
    return tuple(merged)


def build_phase_animation_response(
    sequence: PhaseSearchNode,
    diagnostics: PlannerDiagnostics,
) -> AnimationResponse:
    """Compile coordinated phase steps into the existing frontend event union."""
    events = []
    event_number = 1
    phase_start = 0.0
    # A retained search node stores the *final* analyzed state. After a goal its
    # possession is loose, so it cannot identify the attacking team. The first
    # transition's previous state is the actual root of the selected sequence.
    initial_state = (
        sequence.steps[0].simulation.previous_state
        if sequence.steps
        else sequence.analyzed_state.game_state
    )
    attacking_team_id = initial_state.possession.team_id

    def open_space_snapshot(state, phase_id: str, phase_index: int, at_time: float):
        """Serialize spaces recomputed for one selected phase boundary."""
        if attacking_team_id is None:
            spaces = ()
        elif phase_index == 0:
            # Root analysis already contains spaces computed with its analysis
            # policy, so preserve that exact planner input in the first frame.
            spaces = tuple(
                zone
                for zone in state.target_zones_by_id.values()
                if zone.source == TargetZoneSource.DYNAMIC
                and zone.attacking_team_id == attacking_team_id
            )
        else:
            # Phase simulation returns the new physical state. Recompute its
            # derived spaces for presentation just as state analysis does before
            # expanding the next search depth.
            spaces = discover_dynamic_open_spaces(state, attacking_team_id)
        return {
            "phaseId": phase_id,
            "phaseIndex": phase_index,
            "atTime": _time(at_time),
            "openSpaces": [
                {
                    "id": space.id,
                    "center": {"x": space.center.x, "y": space.center.y},
                    "radius": space.radius or 0,
                }
                for space in spaces
            ],
        }

    phase_snapshots = [
        open_space_snapshot(
            initial_state,
            "initial",
            0,
            0,
        )
    ]

    def next_id() -> str:
        nonlocal event_number
        value = f"action{event_number}"
        event_number += 1
        return value

    def add_turn_event(
        player_id: str,
        start_time: float,
        start_orientation: float,
        target_orientation: float,
    ) -> float:
        difference = abs((target_orientation - start_orientation) % 360)
        if min(difference, 360 - difference) <= 1e-9:
            return 0
        duration = _turn_duration(start_orientation, target_orientation)
        events.append(
            TurnEvent(
                id=next_id(),
                type="TURN",
                player_id=player_id,
                start_time=_time(start_time),
                duration=_time(duration),
                start_orientation=start_orientation,
                target_orientation=target_orientation,
            )
        )
        return duration

    for phase_index, step in enumerate(sequence.steps, start=1):
        phase = step.phase
        action = phase.primary_action
        simulation = step.simulation
        phase_end = phase_start + phase.duration_seconds
        previous_players = simulation.previous_state.players_by_id
        resulting_players = simulation.resulting_state.players_by_id

        for intention in phase.attacking_intentions:
            player = previous_players[intention.player_id]
            resulting = resulting_players[intention.player_id]
            if player.position == resulting.position:
                continue
            turn_duration = add_turn_event(
                player.id,
                phase_start + intention.start_offset_seconds,
                player.orientation,
                resulting.orientation,
            )
            run_start = (
                phase_start
                + intention.start_offset_seconds
                + turn_duration
            )
            # The simulator already caps the resulting destination by maximum
            # speed. Spreading that distance over the remaining phase prevents
            # early arrival followed by an artificial idle pause.
            run_duration = max(0, phase_end - run_start)
            if run_duration <= 0:
                continue
            pace, speed = _run_pace_and_speed(player, resulting.position, run_duration)
            events.append(
                MoveEvent(
                    id=next_id(),
                    type="RUN",
                    player_id=intention.player_id,
                    start_time=_time(run_start),
                    duration=_time(run_duration),
                    target=_position(resulting.position.x, resulting.position.y),
                    pace=pace,
                    speed_cm_per_second=speed,
                )
            )

        for intention in phase.defensive_intentions:
            player = previous_players[intention.player_id]
            resulting = resulting_players[intention.player_id]
            if player.position == resulting.position:
                continue
            turn_duration = add_turn_event(
                player.id,
                phase_start + intention.start_offset_seconds,
                player.orientation,
                resulting.orientation,
            )
            start = (
                phase_start
                + intention.start_offset_seconds
                + turn_duration
            )
            duration = max(0, phase_end - start)
            if duration <= 0:
                continue
            pace, speed = _run_pace_and_speed(player, resulting.position, duration)
            events.append(
                MoveEvent(
                    id=next_id(),
                    type="RUN",
                    player_id=intention.player_id,
                    start_time=_time(start),
                    duration=_time(duration),
                    target=_position(resulting.position.x, resulting.position.y),
                    pace=pace,
                    speed_cm_per_second=speed,
                )
            )

        target = _position(action.destination.x, action.destination.y)
        if action.action_type in {
            ActionType.PASS_TO_SPACE,
            ActionType.PASS_TO_PLAYER,
            ActionType.SHOT,
            ActionType.MOVE_WITH_BALL,
        }:
            actor = previous_players[action.actor_id]
            add_turn_event(
                actor.id,
                phase_start,
                actor.orientation,
                action.source_analysis.orientation_degrees,
            )
        if action.action_type == ActionType.PASS_TO_SPACE:
            raw_duration = action.metrics.ball_travel_duration_seconds or action.metrics.duration_seconds
            pass_start = phase_start + phase.ball_action_start_offset_seconds
            events.append(
                PassToSpaceEvent(
                    id=next_id(),
                    type="PASS_TO_SPACE",
                    player_id=action.actor_id,
                    intended_receiver_id=action.receiver_id,
                    space_id=action.target_zone_id,
                    start_time=_time(pass_start),
                    duration=_time(raw_duration),
                    target=target,
                    pass_category=action.source_analysis.distance_category.value,
                    ball_speed_cm_per_second=action.source_analysis.ball_speed_cm_per_second,
                    receive_time=_time(phase_end),
                )
            )
            events.append(
                ReceiveEvent(
                    id=next_id(), type="RECEIVE",
                    player_id=action.receiver_id,
                    start_time=_time(phase_end),
                )
            )
        elif action.action_type == ActionType.PASS_TO_PLAYER:
            events.append(
                PassEvent(
                    id=next_id(), type="PASS", player_id=action.actor_id,
                    target_player_id=action.receiver_id,
                    start_time=_time(phase_start),
                    duration=_time(phase.duration_seconds),
                    pass_category=action.source_analysis.distance_category.value,
                    ball_speed_cm_per_second=action.source_analysis.ball_speed_cm_per_second,
                    receive_time=_time(phase_end),
                )
            )
            events.append(
                ReceiveEvent(
                    id=next_id(), type="RECEIVE",
                    player_id=action.receiver_id,
                    start_time=_time(phase_end),
                )
            )
        elif action.action_type == ActionType.SHOT:
            raw_duration = (
                action.metrics.ball_travel_duration_seconds
                or action.metrics.duration_seconds
            )
            events.append(
                ShotEvent(
                    id=next_id(), type="SHOT", player_id=action.actor_id,
                    goal_id=action.source_analysis.goal_id,
                    start_time=_time(
                        phase_start + phase.ball_action_start_offset_seconds
                    ),
                    duration=_time(raw_duration),
                    target=target,
                )
            )
        elif action.action_type == ActionType.MOVE_WITH_BALL:
            movement = action.source_analysis
            dribble_speed = (
                action.metrics.distance_cm / movement.travel_duration_seconds
                if movement.travel_duration_seconds > 0
                else 0
            )
            events.append(
                MoveEvent(
                    id=next_id(), type="MOVE_WITH_BALL",
                    player_id=action.actor_id,
                    start_time=_time(
                        phase_start + movement.turn_duration_seconds
                    ),
                    duration=_time(movement.travel_duration_seconds),
                    target=target,
                    pace=movement.pace.value,
                    speed_cm_per_second=dribble_speed,
                )
            )
        phase_snapshots.append(
            open_space_snapshot(
                simulation.resulting_state,
                phase.id,
                phase_index,
                phase_end,
            )
        )
        phase_start = phase_end

    return AnimationResponse(
        duration=_time(phase_start),
        events=_merge_continuous_dribbles(events),
        diagnostics=diagnostics,
        phase_snapshots=tuple(phase_snapshots),
    )
