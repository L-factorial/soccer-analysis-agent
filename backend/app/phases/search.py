from app.analysis_lifecycle import check_analysis_cancelled
from collections import Counter
from dataclasses import dataclass, replace

from app.analysis import game_state_fingerprint
from app.domain import GameState
from app.planning import AnalysisPolicy, AnalyzedGameState, analyze_game_state
from app.planning.beam import BeamPolicy, run_beam_search
from app.phases.models import PhaseSimulationResult, TacticalPhase
from app.phases.offside import OffsidePolicy, check_phase_offside
from app.phases.scoring import PhaseScore
from app.phases.scoring import consecutive_dribble_adjustment
from app.phases.decision_rules import (
    PhaseGenerationPolicy,
    PhaseScoringPolicy,
    generate_tactical_phases,
    score_phase_result,
)
from app.phases.simulation import PhaseSimulationPolicy, simulate_tactical_phase


@dataclass(frozen=True, slots=True)
class PhaseSearchPolicy:
    """Bounds coordinated-phase search latency and future-score contribution."""
    maximum_depth: int = 4
    beam_width: int = 5
    maximum_play_duration_seconds: float = 30
    maximum_retained_nodes: int = 75
    score_discount: float = 0.9
    # Public planning may return the best route plus distinct alternatives.
    # This bounds response/scheduling work; it does not widen the beam itself.
    maximum_solution_count: int = 2

    def __post_init__(self) -> None:
        if self.maximum_depth < 1 or self.beam_width < 1:
            raise ValueError("Phase depth and beam width must be positive")
        if self.maximum_play_duration_seconds <= 0:
            raise ValueError("Maximum play duration must be positive")
        if self.maximum_retained_nodes < 1:
            raise ValueError("Maximum retained nodes must be positive")
        if self.maximum_solution_count < 1:
            raise ValueError("Maximum solution count must be positive")
        if not 0 <= self.score_discount <= 1:
            raise ValueError("Score discount must be between zero and one")


@dataclass(frozen=True, slots=True)
class PhaseSearchStep:
    """Accepted phase edge with simulation and explainable score components."""
    depth: int
    phase: TacticalPhase
    simulation: PhaseSimulationResult
    score: PhaseScore
    discounted_score: float


@dataclass(frozen=True, slots=True)
class PhaseSearchNode:
    """One beam node containing the full selected phase path to its state."""
    id: str
    analyzed_state: AnalyzedGameState
    depth: int
    duration_seconds: float
    cumulative_score: float
    steps: tuple[PhaseSearchStep, ...]


@dataclass(frozen=True, slots=True)
class PhaseSearchDiagnostics:
    """Counters describing generation, rejection, and beam pruning."""
    generated_phase_count: int
    simulated_phase_count: int
    invalid_phase_count: int
    pruned_by_beam_count: int
    pruned_by_duration_count: int
    pruned_by_offside_count: int
    pruned_as_duplicate_count: int
    retained_node_count: int
    reached_depth: int
    invalid_issue_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class PhaseSearchResult:
    """Analyzed root plus score-ordered surviving or terminal sequences."""
    root: AnalyzedGameState
    best_sequences: tuple[PhaseSearchNode, ...]
    diagnostics: PhaseSearchDiagnostics


def _node_order(node: PhaseSearchNode) -> tuple:
    return (
        -node.cumulative_score,
        node.duration_seconds,
        tuple(step.phase.id for step in node.steps),
    )


def search_tactical_phases(
    initial: GameState | AnalyzedGameState,
    search_policy: PhaseSearchPolicy = PhaseSearchPolicy(),
    analysis_policy: AnalysisPolicy = AnalysisPolicy(),
    generation_policy: PhaseGenerationPolicy = PhaseGenerationPolicy(),
    simulation_policy: PhaseSimulationPolicy = PhaseSimulationPolicy(),
    scoring_policy: PhaseScoringPolicy = PhaseScoringPolicy(),
    offside_policy: OffsidePolicy = OffsidePolicy(),
) -> PhaseSearchResult:
    """Adapt coordinated soccer phases to the shared generic beam engine."""
    check_analysis_cancelled()
    root = initial if isinstance(initial, AnalyzedGameState) else analyze_game_state(initial, analysis_policy)
    root_node = PhaseSearchNode("phase-node-000000", root, 0, 0, 0, ())
    generated = simulated = invalid = pruned_beam = pruned_duration = 0
    pruned_offside = pruned_duplicate = 0
    invalid_issues: Counter[str] = Counter()
    next_id = 1

    def expand(parent: PhaseSearchNode, depth: int) -> tuple[PhaseSearchNode, ...]:
        """Generate, validate, simulate, analyze, and score one frontier node."""
        nonlocal generated, simulated, invalid, pruned_duration
        nonlocal pruned_offside, next_id
        check_analysis_cancelled()
        children: list[PhaseSearchNode] = []
        phases = generate_tactical_phases(
            parent.analyzed_state.game_state,
            parent.analyzed_state.action_candidates.feasible,
            generation_policy,
        )
        generated += len(phases)
        for phase in phases:
            check_analysis_cancelled()
            if check_phase_offside(
                parent.analyzed_state.game_state,
                phase,
                offside_policy,
            ).offside:
                pruned_offside += 1
                continue
            duration = parent.duration_seconds + phase.duration_seconds
            if duration > search_policy.maximum_play_duration_seconds:
                pruned_duration += 1
                continue
            simulation = simulate_tactical_phase(
                parent.analyzed_state.game_state,
                phase,
                simulation_policy,
            )
            simulated += 1
            if not simulation.validation.valid:
                invalid += 1
                invalid_issues.update(
                    issue.code.value for issue in simulation.validation.issues
                )
                continue
            analyzed = analyze_game_state(simulation.resulting_state, analysis_policy)
            score = score_phase_result(simulation, scoring_policy)
            # Phase-local scoring rewards progress. Apply the history term here,
            # where the preceding selected phase is available to distinguish a
            # useful tactical change from a repeated same-carrier primitive.
            score = replace(
                score,
                sequence_adjustment=consecutive_dribble_adjustment(
                    parent.steps[-1].phase if parent.steps else None,
                    phase,
                    scoring_policy,
                ),
            )
            discounted = search_policy.score_discount ** (depth - 1) * score.total
            children.append(
                PhaseSearchNode(
                    id=f"phase-node-{next_id:06d}",
                    analyzed_state=analyzed,
                    depth=depth,
                    duration_seconds=duration,
                    cumulative_score=parent.cumulative_score + discounted,
                    steps=(*parent.steps, PhaseSearchStep(depth, phase, simulation, score, discounted)),
                )
            )
            next_id += 1
        return tuple(children)

    beam = run_beam_search(
        root_node,
        BeamPolicy(
            search_policy.maximum_depth,
            search_policy.beam_width,
            search_policy.maximum_retained_nodes,
        ),
        expand=expand,
        state_key=lambda node: game_state_fingerprint(node.analyzed_state.game_state),
        cumulative_score=lambda node: node.cumulative_score,
        node_order=_node_order,
        is_terminal=lambda node: node.analyzed_state.game_state.scored_goal_id is not None,
        depth_of=lambda node: node.depth,
        retain_exhausted_parents=False,
        fallback_to_previous_frontier=True,
    )
    pruned_beam = beam.pruned_by_beam_count
    pruned_duplicate = beam.pruned_as_duplicate_count
    return PhaseSearchResult(
        root=root,
        best_sequences=beam.final_nodes,
        diagnostics=PhaseSearchDiagnostics(
            generated, simulated, invalid, pruned_beam, pruned_duration,
            pruned_offside, pruned_duplicate, beam.retained_node_count,
            beam.reached_depth,
            tuple(sorted(invalid_issues.items())),
        ),
    )
