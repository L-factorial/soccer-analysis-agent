"""Goal-route filtering and diversity rules for public engine results."""

from app.phases import PhaseSearchNode


def sequence_tactical_signature(sequence: PhaseSearchNode) -> tuple:
    """Describe a visible tactical route rather than endpoint-level noise.

    Nearby dynamic-space targets can produce different internal node IDs while
    showing the same actors performing the same play. The signature compares
    action, participants, and broad lateral channel. Repeated identical steps,
    most commonly a long dribble split across phases, collapse into one step.
    """
    signature = []
    for step in sequence.steps:
        action = step.phase.primary_action
        field_width = step.simulation.previous_state.field.width
        lateral_channel = min(2, int(3 * action.destination.y / field_width))
        route_step = (
            action.action_type.value,
            action.actor_id,
            action.receiver_id,
            lateral_channel,
        )
        if not signature or signature[-1] != route_step:
            signature.append(route_step)
    return tuple(signature)


def select_distinct_solutions(
    primary: PhaseSearchNode,
    candidates: tuple[PhaseSearchNode, ...],
    maximum_solution_count: int,
) -> tuple[PhaseSearchNode, ...]:
    """Keep beam-score order while excluding duplicate tactical routes."""
    selected = [primary]
    signatures = {sequence_tactical_signature(primary)}
    for candidate in candidates:
        if candidate.id == primary.id:
            continue
        signature = sequence_tactical_signature(candidate)
        if signature in signatures:
            continue
        selected.append(candidate)
        signatures.add(signature)
        if len(selected) == maximum_solution_count:
            break
    return tuple(selected)
