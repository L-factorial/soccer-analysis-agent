from dataclasses import dataclass
from hashlib import sha256

from app.analysis import ActionCandidate, ActionType
from app.domain import GameState, PossessionStatus
from app.planning.scoring import (
    RankedBranch,
    ScoredActionCandidate,
    ScoredResultingState,
    ScoringPolicy,
    rank_branches,
)
from app.planning.state_analysis import (
    AnalysisPolicy,
    AnalyzedGameState,
    analyze_game_state,
    expand_analyzed_state,
)
from app.transitions import ActionTransition


class InvalidSearchPolicyError(ValueError):
    """Raised when search bounds are invalid."""


@dataclass(frozen=True, slots=True)
class SearchPolicy:
    maximum_depth: int = 3
    beam_width: int = 5
    maximum_sequence_duration_seconds: float = 30
    score_discount: float = 0.9
    maximum_retained_nodes: int = 100
    require_possession_retention: bool = False
    restrict_actions_to_possession_team: bool = True
    maximum_consecutive_off_ball_actions: int = 1

    def __post_init__(self) -> None:
        if self.maximum_depth < 1:
            raise InvalidSearchPolicyError("Maximum depth must be at least one")
        if self.beam_width < 1:
            raise InvalidSearchPolicyError("Beam width must be at least one")
        if self.maximum_sequence_duration_seconds <= 0:
            raise InvalidSearchPolicyError(
                "Maximum sequence duration must be positive"
            )
        if not 0 <= self.score_discount <= 1:
            raise InvalidSearchPolicyError("Score discount must be between zero and one")
        if self.maximum_retained_nodes < 1:
            raise InvalidSearchPolicyError(
                "Maximum retained nodes must be at least one"
            )
        if self.maximum_consecutive_off_ball_actions < 0:
            raise InvalidSearchPolicyError(
                "Maximum consecutive off-ball actions cannot be negative"
            )


@dataclass(frozen=True, slots=True)
class SearchStep:
    depth: int
    candidate: ActionCandidate
    transition: ActionTransition
    immediate_action: ScoredActionCandidate
    resulting_state: ScoredResultingState
    step_score: float
    discounted_score: float


@dataclass(frozen=True, slots=True)
class SearchNode:
    id: str
    depth: int
    parent_node_id: str | None
    analyzed_state: AnalyzedGameState
    step: SearchStep | None
    cumulative_score: float
    elapsed_duration_seconds: float
    path: tuple[SearchStep, ...]


@dataclass(frozen=True, slots=True)
class SearchSequence:
    terminal_node_id: str
    depth: int
    cumulative_score: float
    duration_seconds: float
    steps: tuple[SearchStep, ...]
    resulting_analysis: AnalyzedGameState


@dataclass(frozen=True, slots=True)
class SearchDiagnostics:
    evaluated_child_count: int
    retained_node_count: int
    pruned_by_beam_count: int
    pruned_by_duration_count: int
    pruned_by_possession_count: int
    pruned_as_duplicate_count: int
    pruned_by_node_limit_count: int
    pruned_by_action_pattern_count: int
    reached_depth: int
    stopped_by_node_limit: bool


@dataclass(frozen=True, slots=True)
class SearchResult:
    root: AnalyzedGameState
    best_sequences: tuple[SearchSequence, ...]
    diagnostics: SearchDiagnostics


def _search_state_key(state: GameState) -> str:
    """Identify tactical state while intentionally ignoring elapsed clock time."""
    players = tuple(
        (
            player.id,
            player.position.x,
            player.position.y,
            player.orientation,
            player.speed_category.value,
        )
        for player in sorted(state.players_by_id.values(), key=lambda item: item.id)
    )
    value = (
        players,
        (state.ball.position.x, state.ball.position.y),
        (
            state.possession.status.value,
            state.possession.player_id,
            state.possession.team_id,
            state.possession.contesting_player_ids,
        ),
    )
    return sha256(repr(value).encode("utf-8")).hexdigest()


def _node_order(node: SearchNode) -> tuple:
    return (
        -node.cumulative_score,
        node.elapsed_duration_seconds,
        tuple(step.candidate.id for step in node.path),
        node.id,
    )


def _sequence(node: SearchNode) -> SearchSequence:
    return SearchSequence(
        terminal_node_id=node.id,
        depth=node.depth,
        cumulative_score=node.cumulative_score,
        duration_seconds=node.elapsed_duration_seconds,
        steps=node.path,
        resulting_analysis=node.analyzed_state,
    )


def _is_ball_action(candidate: ActionCandidate) -> bool:
    return candidate.action_type in {
        ActionType.MOVE_WITH_BALL,
        ActionType.PASS_TO_PLAYER,
        ActionType.PASS_TO_SPACE,
        ActionType.SHOT,
    }


def _consecutive_off_ball_actions(
    path: tuple[SearchStep, ...],
    candidate: ActionCandidate,
) -> int:
    if _is_ball_action(candidate):
        return 0
    count = 1
    for step in reversed(path):
        if _is_ball_action(step.candidate):
            break
        count += 1
    return count


def _path_contains_state(parent: SearchNode, state_key: str) -> bool:
    if _search_state_key(parent.analyzed_state.game_state) == state_key:
        return True
    return any(
        _search_state_key(step.transition.previous_state) == state_key
        for step in parent.path
    )


def search_tactical_sequences(
    initial: GameState | AnalyzedGameState,
    search_policy: SearchPolicy = SearchPolicy(),
    analysis_policy: AnalysisPolicy = AnalysisPolicy(),
    scoring_policy: ScoringPolicy = ScoringPolicy(),
) -> SearchResult:
    root = (
        initial
        if isinstance(initial, AnalyzedGameState)
        else analyze_game_state(initial, analysis_policy)
    )
    root_node = SearchNode(
        id="node-000000",
        depth=0,
        parent_node_id=None,
        analyzed_state=root,
        step=None,
        cumulative_score=0,
        elapsed_duration_seconds=0,
        path=(),
    )
    frontier = (root_node,)
    terminal_nodes: list[SearchNode] = []
    best_score_by_state = {_search_state_key(root.game_state): 0.0}
    retained_node_count = 1
    evaluated = 0
    pruned_beam = 0
    pruned_duration = 0
    pruned_possession = 0
    pruned_duplicate = 0
    pruned_limit = 0
    pruned_action_pattern = 0
    reached_depth = 0
    stopped_by_limit = False
    next_node_number = 1
    root_possession_team = root.game_state.possession.team_id

    for depth in range(1, search_policy.maximum_depth + 1):
        next_frontier: list[SearchNode] = []
        for parent in frontier:
            accepted_child = False
            eligible_candidates: list[ActionCandidate] = []
            for candidate in parent.analyzed_state.action_candidates.feasible:
                candidate_team_id = parent.analyzed_state.game_state.players_by_id[
                    candidate.actor_id
                ].team_id
                if (
                    search_policy.restrict_actions_to_possession_team
                    and root_possession_team is not None
                    and candidate_team_id != root_possession_team
                ):
                    pruned_possession += 1
                    continue
                if (
                    _consecutive_off_ball_actions(parent.path, candidate)
                    > search_policy.maximum_consecutive_off_ball_actions
                ):
                    pruned_action_pattern += 1
                    continue
                if (
                    parent.elapsed_duration_seconds
                    + candidate.metrics.duration_seconds
                    > search_policy.maximum_sequence_duration_seconds
                ):
                    pruned_duration += 1
                    continue
                eligible_candidates.append(candidate)

            branches = expand_analyzed_state(
                parent.analyzed_state,
                analysis_policy,
                depth,
                tuple(eligible_candidates),
            )
            ranked = rank_branches(
                parent.analyzed_state,
                branches,
                scoring_policy,
            )
            if not ranked:
                if parent.depth > 0:
                    terminal_nodes.append(parent)
                continue

            for ranked_branch in ranked:
                evaluated += 1
                child_analysis = ranked_branch.branch.resulting_analysis
                elapsed = (
                    child_analysis.game_state.time_seconds
                    - root.game_state.time_seconds
                )
                if elapsed > search_policy.maximum_sequence_duration_seconds:
                    pruned_duration += 1
                    continue
                if (
                    search_policy.require_possession_retention
                    and root_possession_team is not None
                    and child_analysis.game_state.scoring_team_id
                    != root_possession_team
                    and (
                        child_analysis.game_state.possession.status
                        != PossessionStatus.CONTROLLED
                        or child_analysis.game_state.possession.team_id
                        != root_possession_team
                    )
                ):
                    pruned_possession += 1
                    continue

                discounted_score = (
                    search_policy.score_discount ** (depth - 1)
                    * ranked_branch.total_score
                )
                cumulative_score = parent.cumulative_score + discounted_score
                state_key = _search_state_key(child_analysis.game_state)
                if _path_contains_state(parent, state_key):
                    pruned_duplicate += 1
                    continue
                previous_best = best_score_by_state.get(state_key)
                if previous_best is not None and previous_best >= cumulative_score:
                    pruned_duplicate += 1
                    continue
                step = _search_step(depth, ranked_branch, discounted_score)
                node = SearchNode(
                    id=f"node-{next_node_number:06d}",
                    depth=depth,
                    parent_node_id=parent.id,
                    analyzed_state=child_analysis,
                    step=step,
                    cumulative_score=cumulative_score,
                    elapsed_duration_seconds=elapsed,
                    path=(*parent.path, step),
                )
                next_node_number += 1
                next_frontier.append(node)
                accepted_child = True

            if not accepted_child and parent.depth > 0:
                terminal_nodes.append(parent)

        if not next_frontier:
            frontier = ()
            break
        ordered = sorted(next_frontier, key=_node_order)

        # Multiple parent branches can produce the same tactical state at this
        # depth. Keep only the highest-scoring instance before charging nodes
        # against either the beam or the global retention budget.
        unique: list[SearchNode] = []
        pending_state_keys: set[str] = set()
        for node in ordered:
            state_key = _search_state_key(node.analyzed_state.game_state)
            if state_key in pending_state_keys:
                pruned_duplicate += 1
                continue
            pending_state_keys.add(state_key)
            unique.append(node)

        if len(unique) > search_policy.beam_width:
            pruned_beam += len(unique) - search_policy.beam_width
        beam = unique[: search_policy.beam_width]

        remaining_capacity = (
            search_policy.maximum_retained_nodes - retained_node_count
        )
        if len(beam) > remaining_capacity:
            pruned_limit += len(beam) - max(remaining_capacity, 0)
            beam = beam[: max(remaining_capacity, 0)]
            stopped_by_limit = True

        for node in beam:
            best_score_by_state[
                _search_state_key(node.analyzed_state.game_state)
            ] = node.cumulative_score
        retained_node_count += len(beam)
        frontier = tuple(beam)
        reached_depth = depth
        if stopped_by_limit:
            break

    final_nodes = tuple(sorted((*terminal_nodes, *frontier), key=_node_order))
    return SearchResult(
        root=root,
        best_sequences=tuple(_sequence(node) for node in final_nodes),
        diagnostics=SearchDiagnostics(
            evaluated_child_count=evaluated,
            retained_node_count=retained_node_count,
            pruned_by_beam_count=pruned_beam,
            pruned_by_duration_count=pruned_duration,
            pruned_by_possession_count=pruned_possession,
            pruned_as_duplicate_count=pruned_duplicate,
            pruned_by_node_limit_count=pruned_limit,
            pruned_by_action_pattern_count=pruned_action_pattern,
            reached_depth=reached_depth,
            stopped_by_node_limit=stopped_by_limit,
        ),
    )


def _search_step(
    depth: int,
    ranked_branch: RankedBranch,
    discounted_score: float,
) -> SearchStep:
    return SearchStep(
        depth=depth,
        candidate=ranked_branch.branch.selected_candidate,
        transition=ranked_branch.branch.transition,
        immediate_action=ranked_branch.immediate_action,
        resulting_state=ranked_branch.resulting_state,
        step_score=ranked_branch.total_score,
        discounted_score=discounted_score,
    )
