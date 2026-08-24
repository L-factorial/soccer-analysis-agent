import os
import unittest
from unittest.mock import Mock, patch

from app.api.field_configurations import CommentaryRequest
from app.commentary.models import (
    CommentarySimulationInput,
    GeneratedCommentary,
    GeneratedPhaseCommentary,
)
from app.commentary.service import generate_commentary
from app.models.animation_response import (
    AnimationResponse,
    PlannerDiagnostics,
    SelectedPhaseDiagnostic,
)
from app.models.field_submission import FieldSubmission
from app.models.position import Position
from test_field_submission_validation import valid_payload


def _response() -> AnimationResponse:
    phase = SelectedPhaseDiagnostic(
        id="phase-1",
        phase_type="PASS_PHASE",
        action_type="PASS_TO_PLAYER",
        actor_id="team1-1",
        receiver_id="team1-2",
        target_zone_id=None,
        target=Position(x=3000, y=4000),
        start_time=1,
        duration=2,
        end_time=3,
        ball_action_start_time=1,
        possession_before="team1-1",
        possession_after="team1-2",
        score=10,
        scored_goal=False,
    )
    diagnostics = PlannerDiagnostics(
        attacking_team_id="team1",
        reached_depth=1,
        evaluated_candidate_count=1,
        root_candidate_count=1,
        root_feasible_candidate_count=1,
        pruned_by_beam_count=0,
        pruned_by_duration_count=0,
        pruned_by_possession_count=0,
        pruned_by_action_pattern_count=0,
        rejection_reasons={},
        dynamic_spaces=(),
        selected_phases=(phase,),
    )
    return AnimationResponse(duration=3, events=(), diagnostics=diagnostics)


def _commentary_input() -> CommentarySimulationInput:
    return CommentarySimulationInput.model_validate(
        _response().model_dump(by_alias=True)
    )


class CommentaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.submission = FieldSubmission.model_validate(valid_payload())

    @patch.dict(os.environ, {"SOCCER_COMMENTARY_ENABLED": "false"}, clear=False)
    def test_disabled_commentary_returns_original_response(self) -> None:
        self.assertIsNone(generate_commentary(_commentary_input(), self.submission))

    def test_request_accepts_camel_case_animation_returned_by_frontend(self) -> None:
        request = CommentaryRequest.model_validate(
            {
                "fieldSubmission": valid_payload(),
                "animationResponse": _response().model_dump(by_alias=True),
            }
        )
        self.assertEqual(
            request.animation_response.diagnostics.selected_phases[0].start_time,
            1,
        )

    @patch.dict(
        os.environ,
        {"SOCCER_COMMENTARY_ENABLED": "true", "OPENAI_API_KEY": "test-key"},
        clear=False,
    )
    @patch("app.commentary.service.OpenAI")
    def test_generated_text_uses_authoritative_phase_timing(self, client: Mock) -> None:
        parsed = GeneratedCommentary(
            title="A quick opening",
            summary="The attack moves the ball forward.",
            phases=(
                GeneratedPhaseCommentary(
                    phase_id="phase-1",
                    text="The midfielder releases a sharp forward pass.",
                ),
            ),
        )
        client.return_value.responses.parse.return_value.output_parsed = parsed

        commentary = generate_commentary(_commentary_input(), self.submission)

        self.assertIsNotNone(commentary)
        cue = commentary.cues[0]
        self.assertEqual(cue.start_time, 1)
        self.assertEqual(cue.end_time, 3)
        self.assertEqual(cue.phase_id, "phase-1")
        prompt = client.return_value.responses.parse.call_args.kwargs["input"][0][
            "content"
        ]
        self.assertIn("live soccer match", prompt)
        self.assertIn("fast-moving play-by-play", prompt)
        self.assertIn("classic radio-broadcast", prompt)
        self.assertIn("listener cannot see the field", prompt)
        self.assertIn("avoid catchphrases", prompt)
        self.assertIn("action-packed", prompt)
        self.assertIn("Here they come!", prompt)
        self.assertIn("post-goal coda", prompt)
        self.assertIn("poetry in motion", prompt)
        self.assertIn("clinical finish", prompt)
        self.assertIn("creative palette rather than a checklist", prompt)


if __name__ == "__main__":
    unittest.main()
