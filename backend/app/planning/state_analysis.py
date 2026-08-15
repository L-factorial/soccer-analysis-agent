from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.analysis import (
    ActionCandidate,
    ActionCandidateSet,
    DynamicSpacePolicy,
    MovementPolicy,
    PassPolicy,
    PlayerContext,
    PossessionAnalysis,
    PossessionPolicy,
    PressurePolicy,
    TargetZoneAnalysis,
    TargetZonePolicy,
    analyze_all_players,
    analyze_all_target_zones,
    generate_action_candidates,
    game_state_fingerprint,
    resolve_initial_possession,
    with_dynamic_open_spaces,
)
from app.domain import GameState
from app.transitions import ActionTransition, apply_action_candidate


@dataclass(frozen=True, slots=True)
class AnalysisPolicy:
    possession: PossessionPolicy = PossessionPolicy()
    pressure: PressurePolicy = PressurePolicy()
    target_zones: TargetZonePolicy = TargetZonePolicy()
    movement: MovementPolicy = MovementPolicy()
    passing: PassPolicy = PassPolicy()
    dynamic_spaces: DynamicSpacePolicy = DynamicSpacePolicy()


@dataclass(frozen=True, slots=True)
class AnalysisDiagnostics:
    player_count: int
    team_count: int
    target_zone_count: int
    candidate_count: int
    feasible_candidate_count: int
    rejected_candidate_count: int


@dataclass(frozen=True, slots=True)
class AnalyzedGameState:
    game_state: GameState
    state_fingerprint: str
    possession: PossessionAnalysis
    player_contexts: Mapping[str, PlayerContext]
    target_zones_by_team: Mapping[str, Mapping[str, TargetZoneAnalysis]]
    action_candidates: ActionCandidateSet
    diagnostics: AnalysisDiagnostics


@dataclass(frozen=True, slots=True)
class BranchExpansion:
    id: str
    depth: int
    parent_state_fingerprint: str
    selected_candidate: ActionCandidate
    transition: ActionTransition
    resulting_analysis: AnalyzedGameState


def analyze_game_state(
    state: GameState,
    policy: AnalysisPolicy = AnalysisPolicy(),
) -> AnalyzedGameState:
    """Resolve and recompute every deterministic analysis for one state."""
    resolved_state, possession = resolve_initial_possession(
        state,
        policy.possession,
    )
    resolved_state = with_dynamic_open_spaces(
        resolved_state,
        policy.dynamic_spaces,
    )
    player_contexts = analyze_all_players(resolved_state, policy.pressure)
    target_zones_by_team = MappingProxyType(
        {
            team_id: analyze_all_target_zones(
                resolved_state,
                team_id,
                policy.target_zones,
            )
            for team_id in sorted(resolved_state.teams_by_id)
        }
    )
    candidates = generate_action_candidates(
        resolved_state,
        policy.movement,
        policy.passing,
    )
    if resolved_state.scored_goal_id is not None:
        candidates = ActionCandidateSet(all=(), feasible=(), rejected=())
    return AnalyzedGameState(
        game_state=resolved_state,
        state_fingerprint=game_state_fingerprint(resolved_state),
        possession=possession,
        player_contexts=player_contexts,
        target_zones_by_team=target_zones_by_team,
        action_candidates=candidates,
        diagnostics=AnalysisDiagnostics(
            player_count=len(resolved_state.players_by_id),
            team_count=len(resolved_state.teams_by_id),
            target_zone_count=len(resolved_state.target_zones_by_id),
            candidate_count=len(candidates.all),
            feasible_candidate_count=len(candidates.feasible),
            rejected_candidate_count=len(candidates.rejected),
        ),
    )


def expand_analyzed_state(
    analyzed_state: AnalyzedGameState,
    policy: AnalysisPolicy = AnalysisPolicy(),
    depth: int = 1,
    candidates: tuple[ActionCandidate, ...] | None = None,
) -> tuple[BranchExpansion, ...]:
    """Apply and fully reanalyze each feasible action as one child branch."""
    if depth < 1:
        raise ValueError("Branch depth must be at least one")

    return tuple(
        _expand_candidate(
            analyzed_state,
            candidate,
            policy,
            depth,
            index,
        )
        for index, candidate in enumerate(
            candidates
            if candidates is not None
            else analyzed_state.action_candidates.feasible,
            start=1,
        )
    )


def _expand_candidate(
    analyzed_state: AnalyzedGameState,
    candidate: ActionCandidate,
    policy: AnalysisPolicy,
    depth: int,
    index: int,
) -> BranchExpansion:
    transition = apply_action_candidate(analyzed_state.game_state, candidate)
    resulting_analysis = analyze_game_state(
        transition.resulting_state,
        policy,
    )
    return BranchExpansion(
        id=f"branch-{depth:02d}-{index:04d}",
        depth=depth,
        parent_state_fingerprint=analyzed_state.state_fingerprint,
        selected_candidate=candidate,
        transition=transition,
        resulting_analysis=resulting_analysis,
    )
