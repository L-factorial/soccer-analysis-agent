"""Production configuration for the deterministic game engine."""

from app.phases import PhaseSearchPolicy


def default_phase_search_policy() -> PhaseSearchPolicy:
    """Return the search limits used by the public analysis endpoint.

    Keeping production limits here makes the engine reusable from HTTP, tests,
    or a future command-line runner without duplicating endpoint configuration.
    A new policy object is returned on every call even though it is immutable.
    """
    return PhaseSearchPolicy(
        maximum_depth=8,
        # Retain more competing tactical routes so a distinct second goal plan
        # has a realistic chance to survive solution selection.
        beam_width=8,
        maximum_play_duration_seconds=30,
        maximum_retained_nodes=100,
        maximum_solution_count=2,
    )
