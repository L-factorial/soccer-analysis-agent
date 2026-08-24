import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.api.field_configurations import (
    _select_distinct_solutions,
    _sequence_tactical_signature,
    analyze_field_configuration,
    receive_field_configuration,
)
from app.models.field_submission import FieldSubmission
from app.validation import FieldSubmissionValidationError, validate_field_submission


def valid_payload() -> dict:
    return {
        "schemaVersion": "1.0",
        "fieldConfiguration": {
            "label": "5v5",
            "fieldType": "5v5",
            "dimensions": {"length": 12000, "width": 9000, "unit": "cm"},
            "goalDimensions": {"length": 200, "width": 2400, "unit": "cm"},
            "teams": [
                {
                    "id": "team1",
                    "name": "team1",
                    "color": "#D8FF3E",
                    "defendedGoalId": "goal-left",
                },
                {
                    "id": "team2",
                    "name": "team2",
                    "color": "#FF725E",
                    "defendedGoalId": "goal-right",
                },
            ],
            "goals": [
                {
                    "id": "goal-left",
                    "name": "Goal1",
                    "side": "left",
                    "coordinates": [
                        {"x": 0, "y": 3300},
                        {"x": 200, "y": 3300},
                        {"x": 200, "y": 5700},
                        {"x": 0, "y": 5700},
                    ],
                },
                {
                    "id": "goal-right",
                    "name": "Goal2",
                    "side": "right",
                    "coordinates": [
                        {"x": 11800, "y": 3300},
                        {"x": 12000, "y": 3300},
                        {"x": 12000, "y": 5700},
                        {"x": 11800, "y": 5700},
                    ],
                },
            ],
            "players": [
                {
                    "id": "team1-1",
                    "name": "team1-1",
                    "number": 1,
                    "teamId": "team1",
                    "position": {"x": 2000, "y": 4500},
                    "orientation": 0,
                    "velocity": {"x": 0, "y": 0},
                }
            ],
            "ball": {
                "position": {"x": 6000, "y": 4500},
                "direction": 0,
                "speed": 0,
            },
            "openSpaces": [],
        },
    }


def tactical_sequence(sequence_id: str, destinations: tuple[tuple[float, float], ...]):
    """Build the minimum phase shape needed by alternative-route comparison."""
    steps = []
    for x, y in destinations:
        action = SimpleNamespace(
            action_type=SimpleNamespace(value="MOVE_WITH_BALL"),
            actor_id="team1-7",
            receiver_id=None,
            destination=SimpleNamespace(x=x, y=y),
        )
        steps.append(
            SimpleNamespace(
                phase=SimpleNamespace(primary_action=action),
                simulation=SimpleNamespace(
                    previous_state=SimpleNamespace(
                        field=SimpleNamespace(width=9000.0)
                    )
                ),
            )
        )
    return SimpleNamespace(id=sequence_id, steps=tuple(steps))


class AlternativeRouteSelectionTests(unittest.TestCase):
    def test_nearby_endpoints_and_split_dribbles_are_the_same_route(self):
        primary = tactical_sequence("primary", ((5000, 1700),))
        near_duplicate = tactical_sequence(
            "near-duplicate",
            ((5400, 1900), (5900, 2100)),
        )

        self.assertEqual(
            _sequence_tactical_signature(primary),
            _sequence_tactical_signature(near_duplicate),
        )
        self.assertEqual(
            _select_distinct_solutions(primary, (near_duplicate,), 2),
            (primary,),
        )

    def test_a_different_attacking_channel_is_retained(self):
        primary = tactical_sequence("primary", ((5000, 1700),))
        opposite_channel = tactical_sequence("opposite", ((5000, 7400),))

        self.assertEqual(
            _select_distinct_solutions(primary, (opposite_channel,), 2),
            (primary, opposite_channel),
        )


class FieldSubmissionValidationTests(unittest.TestCase):
    def test_accepts_separate_optional_player_profile_name(self):
        payload = valid_payload()
        payload["fieldConfiguration"]["players"][0]["profileName"] = "Alex"

        submission = FieldSubmission.model_validate(payload)

        self.assertEqual(
            submission.field_configuration.players[0].name,
            "team1-1",
        )
        self.assertEqual(
            submission.field_configuration.players[0].profile_name,
            "Alex",
        )

    def test_accepts_valid_static_field(self) -> None:
        submission = FieldSubmission.model_validate(valid_payload())

        self.assertIsNone(validate_field_submission(submission))

    def test_collects_multiple_domain_issues(self) -> None:
        payload = valid_payload()
        field = payload["fieldConfiguration"]
        field["players"].append(
            {
                **field["players"][0],
                "id": "team2-1",
                "teamId": "missing-team",
                "position": {"x": 13000, "y": 4500},
                "velocity": {"x": 2, "y": 0},
            }
        )
        field["ball"]["speed"] = 10
        submission = FieldSubmission.model_validate(payload)

        with self.assertRaises(FieldSubmissionValidationError) as context:
            validate_field_submission(submission)

        codes = {issue.code for issue in context.exception.issues}
        self.assertTrue(
            {
                "unknown_player_team",
                "player_outside_field",
                "nonzero_initial_velocity",
                "nonzero_initial_ball_speed",
            }.issubset(codes)
        )

    def test_rejects_space_extending_outside_field(self) -> None:
        payload = valid_payload()
        payload["fieldConfiguration"]["openSpaces"] = [
            {
                "id": "OpenSpace1",
                "name": "OpenSpace1",
                "type": "circular",
                "center": {"x": 100, "y": 100},
                "radius": 200,
            }
        ]
        submission = FieldSubmission.model_validate(payload)

        with self.assertRaises(FieldSubmissionValidationError) as context:
            validate_field_submission(submission)

        self.assertIn(
            "open_space_outside_field",
            {issue.code for issue in context.exception.issues},
        )


class FieldSubmissionEndpointTests(unittest.TestCase):
    def test_endpoint_returns_structured_validation_errors(self) -> None:
        payload = valid_payload()
        payload["fieldConfiguration"]["players"][0]["velocity"] = {
            "x": 1,
            "y": 0,
        }
        submission = FieldSubmission.model_validate(payload)

        with self.assertRaises(HTTPException) as context:
            receive_field_configuration(submission)

        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(
            context.exception.detail["code"],
            "invalid_field_configuration",
        )


if __name__ == "__main__":
    unittest.main()
