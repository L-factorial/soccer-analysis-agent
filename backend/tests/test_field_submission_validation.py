import unittest

from fastapi import HTTPException

from app.api.field_configurations import receive_field_configuration
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


class FieldSubmissionValidationTests(unittest.TestCase):
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
