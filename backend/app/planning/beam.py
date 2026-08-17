from dataclasses import dataclass
from typing import Callable, Generic, TypeVar


NodeT = TypeVar("NodeT")


@dataclass(frozen=True, slots=True)
class BeamPolicy:
    """Domain-independent depth, width, and retained-node bounds."""
    maximum_depth: int
    beam_width: int
    maximum_retained_nodes: int


@dataclass(frozen=True, slots=True)
class BeamSearchOutcome(Generic[NodeT]):
    """Final frontier/terminal nodes plus pruning counters from traversal."""
    final_nodes: tuple[NodeT, ...]
    retained_node_count: int
    pruned_by_beam_count: int
    pruned_as_duplicate_count: int
    pruned_by_node_limit_count: int
    reached_depth: int
    stopped_by_node_limit: bool


def run_beam_search(
    root: NodeT,
    policy: BeamPolicy,
    *,
    expand: Callable[[NodeT, int], tuple[NodeT, ...]],
    state_key: Callable[[NodeT], str],
    cumulative_score: Callable[[NodeT], float],
    node_order: Callable[[NodeT], tuple],
    is_terminal: Callable[[NodeT], bool],
    depth_of: Callable[[NodeT], int],
    retain_exhausted_parents: bool,
    fallback_to_previous_frontier: bool,
) -> BeamSearchOutcome[NodeT]:
    """Run deterministic beam traversal independently of tactical rules.

    Domain adapters own generation, simulation, validation, and scoring. This
    engine owns frontier traversal, state de-duplication, beam pruning, and the
    global retained-node budget.
    """
    frontier = (root,)
    terminal_nodes: list[NodeT] = []
    best_score_by_state = {state_key(root): cumulative_score(root)}
    retained = 1
    pruned_beam = pruned_duplicate = pruned_limit = 0
    reached_depth = 0
    stopped_by_limit = False

    for depth in range(1, policy.maximum_depth + 1):
        previous_frontier = frontier
        children: list[NodeT] = []
        for parent in frontier:
            if is_terminal(parent):
                terminal_nodes.append(parent)
                continue
            expanded = expand(parent, depth)
            if not expanded and retain_exhausted_parents and depth_of(parent) > 0:
                terminal_nodes.append(parent)
            for child in expanded:
                key = state_key(child)
                if best_score_by_state.get(key, float("-inf")) >= cumulative_score(child):
                    pruned_duplicate += 1
                    continue
                children.append(child)

        if not children:
            frontier = previous_frontier if fallback_to_previous_frontier else ()
            break

        unique: list[NodeT] = []
        pending_keys: set[str] = set()
        for node in sorted(children, key=node_order):
            key = state_key(node)
            if key in pending_keys:
                pruned_duplicate += 1
                continue
            pending_keys.add(key)
            unique.append(node)

        if len(unique) > policy.beam_width:
            pruned_beam += len(unique) - policy.beam_width
        beam = unique[: policy.beam_width]
        remaining_capacity = policy.maximum_retained_nodes - retained
        if len(beam) > remaining_capacity:
            pruned_limit += len(beam) - max(remaining_capacity, 0)
            beam = beam[: max(remaining_capacity, 0)]
            stopped_by_limit = True

        frontier = tuple(beam)
        for node in frontier:
            best_score_by_state[state_key(node)] = cumulative_score(node)
        retained += len(frontier)
        reached_depth = depth
        if not frontier or stopped_by_limit:
            break

    return BeamSearchOutcome(
        final_nodes=tuple(sorted((*terminal_nodes, *frontier), key=node_order)),
        retained_node_count=retained,
        pruned_by_beam_count=pruned_beam,
        pruned_as_duplicate_count=pruned_duplicate,
        pruned_by_node_limit_count=pruned_limit,
        reached_depth=reached_depth,
        stopped_by_node_limit=stopped_by_limit,
    )
