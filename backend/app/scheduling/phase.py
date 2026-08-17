from app.builders.phase_animation_response import build_phase_animation_response
from app.models.animation_response import AnimationResponse, PlannerDiagnostics
from app.phases import PhaseSearchNode


class PhaseAnimationScheduler:
    """Schedule a selected plan onto the frontend animation timeline.

    This boundary intentionally accepts an already selected search node. It has
    no access to tactical policies and therefore cannot change the chosen play.
    """

    def schedule(
        self,
        sequence: PhaseSearchNode,
        diagnostics: PlannerDiagnostics,
    ) -> AnimationResponse:
        return build_phase_animation_response(sequence, diagnostics)
