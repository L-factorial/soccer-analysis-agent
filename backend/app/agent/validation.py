from app.agent.models import TacticalIntent, TacticalObservation


def validate_intent_references(
    intent: TacticalIntent,
    observation: TacticalObservation,
) -> TacticalIntent:
    """Remove hallucinated references while preserving the valid strategy."""
    attacker_ids = {
        player["id"]
        for player in observation.players
        if player["teamId"] == observation.attacking_team_id
    }
    space_ids = {space["id"] for space in observation.spaces}
    feasible_types = set(observation.feasible_action_types)
    return intent.model_copy(
        update={
            "preferred_player_ids": [
                player_id
                for player_id in intent.preferred_player_ids
                if player_id in attacker_ids
            ],
            "preferred_space_ids": [
                space_id for space_id in intent.preferred_space_ids
                if space_id in space_ids
            ],
            "preferred_action_types": [
                action_type for action_type in intent.preferred_action_types
                if action_type in feasible_types
            ],
        }
    )
