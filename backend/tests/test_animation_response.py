import unittest

from app.api.field_configurations import analyze_field_configuration
from app.builders import build_animation_response
from app.models.field_submission import FieldSubmission
from app.analysis import ActionType
from app.planning import SearchPolicy, search_tactical_sequences
from test_action_candidates import build_state
from test_field_submission_validation import valid_payload


class AnimationResponseBuilderTests(unittest.TestCase):
    def test_builds_frontend_contract_with_cumulative_times(self) -> None:
        search = search_tactical_sequences(
            build_state(resolve=False),
            SearchPolicy(maximum_depth=2, beam_width=2),
        )
        sequence = search.best_sequences[0]
        response = build_animation_response(sequence)
        payload = response.model_dump(by_alias=True)

        self.assertAlmostEqual(response.duration, sequence.duration_seconds, places=6)
        self.assertTrue(response.events)
        self.assertEqual(
            tuple(event["id"] for event in payload["events"]),
            tuple(f"action{index}" for index in range(1, len(response.events) + 1)),
        )
        self.assertIn("playerId", payload["events"][0])
        self.assertIn("startTime", payload["events"][0])
        self.assertTrue(
            any(
                event["type"] == "RUN" and event["playerId"].startswith("team2-")
                for event in payload["events"]
            )
        )
        self.assertLessEqual(
            max(
                event["startTime"] + event.get("duration", 0)
                for event in payload["events"]
            ),
            payload["duration"] + 1e-6,
        )

    def test_space_pass_synchronizes_run_pass_and_receive_arrival(self) -> None:
        search = search_tactical_sequences(
            build_state(resolve=False),
            SearchPolicy(maximum_depth=1, beam_width=50),
        )
        sequence = next(
            sequence
            for sequence in search.best_sequences
            if sequence.steps[0].candidate.action_type == ActionType.PASS_TO_SPACE
            and sequence.steps[0].candidate.target_zone_id == "OpenSpace2"
        )
        payload = build_animation_response(sequence).model_dump(by_alias=True)
        pass_event = next(
            event for event in payload["events"] if event["type"] == "PASS_TO_SPACE"
        )
        receive_event = next(
            event for event in payload["events"] if event["type"] == "RECEIVE"
        )
        run_event = next(
            event
            for event in payload["events"]
            if event["type"] == "RUN"
            and event["playerId"] == pass_event["intendedReceiverId"]
        )

        self.assertLess(run_event["startTime"], pass_event["startTime"])
        self.assertAlmostEqual(
            run_event["startTime"] + run_event["duration"],
            receive_event["startTime"],
            places=5,
        )
        self.assertAlmostEqual(
            pass_event["startTime"] + pass_event["duration"],
            receive_event["startTime"],
            places=5,
        )


class AnalyzeEndpointTests(unittest.TestCase):
    def test_returns_animation_for_valid_controlling_layout(self) -> None:
        payload = valid_payload()
        field = payload["fieldConfiguration"]
        field["players"][0]["position"] = {"x": 10500, "y": 4500}
        field["ball"]["position"] = {"x": 10500, "y": 4500}
        field["players"].append(
            {
                "id": "team1-2",
                "name": "team1-2",
                "number": 2,
                "teamId": "team1",
                "position": {"x": 11000, "y": 4500},
                "orientation": 0,
                "velocity": {"x": 0, "y": 0},
            }
        )
        response = analyze_field_configuration(
            FieldSubmission.model_validate(payload)
        )

        self.assertGreater(response.duration, 0)
        self.assertTrue(response.events)
        diagnostics = response.model_dump(by_alias=True)["diagnostics"]
        self.assertTrue(diagnostics["selectedPhases"])
        self.assertIn("ballActionStartTime", diagnostics["selectedPhases"][0])
        self.assertIn("offsideLineX", diagnostics["selectedPhases"][0])


if __name__ == "__main__":
    unittest.main()
