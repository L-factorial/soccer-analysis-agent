from collections import Counter
from dataclasses import dataclass

from app.analysis import game_state_fingerprint
from app.domain import GameState
from app.planning import AnalysisPolicy, AnalyzedGameState, analyze_game_state
from app.phases.models import PhaseSimulationResult, TacticalPhase
from app.phases.offside import OffsidePolicy, check_phase_offside
from app.phases.scoring import PhaseScore, PhaseScoringPolicy, score_phase_result
from app.phases.simulation import PhaseSimulationPolicy, simulate_tactical_phase
from app.phases.templates import PhaseGenerationPolicy, generate_tactical_phases


@dataclass(frozen=True, slots=True)
class PhaseSearchPolicy:
    maximum_depth: int = 4
    beam_width: int = 5
    maximum_play_duration_seconds: float = 30
    maximum_retained_nodes: int = 75
    score_discount: float = 0.9

    def __post_init__(self) -> None:
        if self.maximum_depth < 1 or self.beam_width < 1:
            raise ValueError("Phase depth and beam width must be positive")
        if self.maximum_play_duration_seconds <= 0:
            raise ValueError("Maximum play duration must be positive")
        if self.maximum_retained_nodes < 1:
            raise ValueError("Maximum retained nodes must be positive")
        if not 0 <= self.score_discount <= 1:
            raise ValueError("Score discount must be between zero and one")


@dataclass(frozen=True, slots=True)
class PhaseSearchStep:
    depth: int
    phase: TacticalPhase
    simulation: PhaseSimulationResult
    score: PhaseScore
    discounted_score: float


@dataclass(frozen=True, slots=True)
class PhaseSearchNode:
    id: str
    analyzed_state: AnalyzedGameState
    depth: int
    duration_seconds: float
    cumulative_score: float
    steps: tuple[PhaseSearchStep, ...]


@dataclass(frozen=True, slots=True)
class PhaseSearchDiagnostics:
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
    root = initial if isinstance(initial, AnalyzedGameState) else analyze_game_state(initial, analysis_policy)
    frontier = (
        PhaseSearchNode("phase-node-000000", root, 0, 0, 0, ()),
    )
    terminal: list[PhaseSearchNode] = []
    retained = 1
    generated = simulated = invalid = pruned_beam = pruned_duration = 0
    pruned_offside = pruned_duplicate = 0
    invalid_issues: Counter[str] = Counter()
    reached_depth = 0
    next_id = 1
    best_score_by_state = {game_state_fingerprint(root.game_state): 0.0}

    for depth in range(1, search_policy.maximum_depth + 1):
        children: list[PhaseSearchNode] = []
        for parent in frontier:
            if parent.analyzed_state.game_state.scored_goal_id is not None:
                terminal.append(parent)
                continue
            phases = generate_tactical_phases(
                parent.analyzed_state.game_state,
                parent.analyzed_state.action_candidates.feasible,
                generation_policy,
            )
            generated += len(phases)
            for phase in phases:
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
                discounted = search_policy.score_discount ** (depth - 1) * score.total
                cumulative = parent.cumulative_score + discounted
                key = game_state_fingerprint(analyzed.game_state)
                if best_score_by_state.get(key, float("-inf")) >= cumulative:
                    pruned_duplicate += 1
                    continue
                children.append(
                    PhaseSearchNode(
                        id=f"phase-node-{next_id:06d}",
                        analyzed_state=analyzed,
                        depth=depth,
                        duration_seconds=duration,
                        cumulative_score=cumulative,
                        steps=(*parent.steps, PhaseSearchStep(depth, phase, simulation, score, discounted)),
                    )
                )
                next_id += 1

        if not children:
            break
        unique: list[PhaseSearchNode] = []
        seen: set[str] = set()
        for node in sorted(children, key=_node_order):
            key = game_state_fingerprint(node.analyzed_state.game_state)
            if key in seen:
                pruned_duplicate += 1
                continue
            seen.add(key)
            unique.append(node)
        if len(unique) > search_policy.beam_width:
            pruned_beam += len(unique) - search_policy.beam_width
        capacity = search_policy.maximum_retained_nodes - retained
        frontier = tuple(unique[: min(search_policy.beam_width, max(0, capacity))])
        for node in frontier:
            best_score_by_state[game_state_fingerprint(node.analyzed_state.game_state)] = node.cumulative_score
        retained += len(frontier)
        reached_depth = depth
        if not frontier or retained >= search_policy.maximum_retained_nodes:
            break

    ordered = tuple(sorted((*terminal, *frontier), key=_node_order))
    return PhaseSearchResult(
        root=root,
        best_sequences=ordered,
        diagnostics=PhaseSearchDiagnostics(
            generated, simulated, invalid, pruned_beam, pruned_duration,
            pruned_offside, pruned_duplicate, retained, reached_depth,
            tuple(sorted(invalid_issues.items())),
        ),
    )
