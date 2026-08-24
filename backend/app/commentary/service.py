"""Generate commentary after the authoritative animation has been scheduled.

This module is intentionally read-only. The model sees a compact projection of
the selected plan and may only write prose for existing phase IDs. Backend-owned
timestamps are attached after generation, so model output cannot change the
simulation timeline.
"""

import json
import logging
import os

from openai import OpenAI

from app.commentary.config import CommentaryConfig
from app.commentary.models import CommentarySimulationInput, GeneratedCommentary
from app.models.animation_response import (
    CommentaryCue,
    CommentaryTrack,
)
from app.models.field_submission import FieldSubmission

logger = logging.getLogger("uvicorn.error")


def _commentary_input(
    response: CommentarySimulationInput,
    submission: FieldSubmission,
) -> str:
    """Return only facts needed for narration, excluding search telemetry."""
    phases = response.diagnostics.selected_phases if response.diagnostics else ()
    names = {
        player.id: player.profile_name or player.name
        for player in submission.field_configuration.players
    }
    phase_payloads = []
    for index, phase in enumerate(phases):
        item = phase.model_dump(by_alias=True)
        # About 2.2 spoken words per second keeps browser narration inside the
        # phase window. The closing call receives a larger coda budget because
        # continuous narration may outlive the animation to recap the goal and
        # credit the players who created it.
        closing_grace_words = 24 if index == len(phases) - 1 else 0
        item["commentaryWordBudget"] = max(
            4,
            int(phase.duration * 2.2) + closing_grace_words,
        )
        phase_payloads.append(item)
    payload = {
        "durationSeconds": response.duration,
        "players": names,
        "phases": phase_payloads,
        "events": response.events,
    }
    return json.dumps(payload, separators=(",", ":"))


def generate_commentary(
    response: CommentarySimulationInput,
    submission: FieldSubmission,
) -> CommentaryTrack | None:
    """Generate a read-only track or return ``None`` when unavailable."""
    config = CommentaryConfig.from_environment()
    if not config.enabled or not os.getenv("OPENAI_API_KEY"):
        return None

    phases = response.diagnostics.selected_phases if response.diagnostics else ()
    phase_by_id = {phase.id: phase for phase in phases}
    if not phase_by_id:
        return None

    try:
        generated = OpenAI(timeout=config.timeout_seconds).responses.parse(
            model=config.model,
            input=[
                {
                    "role": "developer",
                    "content": (
                        "You are calling a live soccer match in an original classic "
                        "radio-broadcast style. The listener cannot see the field, so "
                        "turn the supplied simulation into clear, continuous, fast-"
                        "moving play-by-play—not a technical report or coaching lesson. "
                        "Regularly identify who has the ball, the direction of the move, "
                        "and the immediate pressure or available space. Use compact "
                        "phrases, strong rhythm, and quick transitions; accelerate the "
                        "language as the attack reaches goal, then give an emotionally "
                        "satisfying release only when a goal is actually scored. Use "
                        "short em-dash pauses for breath, but avoid catchphrases, "
                        "quotations, imitation of any real commentator, or ornate "
                        "language on routine movements. "
                        "Make decisive actions punchy and action-packed. Favor muscular "
                        "verbs and compact broadcast phrases such as surges forward, "
                        "bursts into space, darts beyond, threads it through, zips it "
                        "wide, whips it across, shuts the door, bears down on goal, "
                        "pulls the trigger, and rifles it home—but only when the exact "
                        "action is supported by the data. Use brief exclamations such "
                        "as Here they come!, What a run!, Chance!, and GOAL! sparingly "
                        "at genuinely important moments. Never call a routine pass a "
                        "shot, cross, tackle, save, or goal. Vary "
                        "the poetic broadcast vocabulary when the play earns it. Draw "
                        "from ideas such as firing on all cylinders, poetry in motion, "
                        "a pass painted through the defense, the move opens like a map, "
                        "a run timed to perfection, the defense is pulled apart, what "
                        "a pass, what a play, an inspired assist, a devastating final "
                        "ball, composure under pressure, a clinical finish, precision "
                        "at full speed, and a move of real quality. Treat this as a "
                        "creative palette rather than a checklist: paraphrase, rotate, "
                        "and use at most one heightened image per phase so the call "
                        "sounds spontaneous rather than repetitive or exaggerated. Vary "
                        "sentence openings and build excitement as the attack reaches "
                        "the goal. Prefer profile names; otherwise use a natural shirt-"
                        "number reference instead of internal IDs where possible. "
                        "Produce one crisp spoken cue for every supplied phase, use "
                        "each exact phase ID once, and strictly respect each "
                        "commentaryWordBudget. Use the final phase's larger budget for "
                        "a brief post-goal coda: describe how the move developed and "
                        "credit the scorer, provider, or supporting runners only when "
                        "their contribution is present in the supplied events. The title "
                        "and summary should sound like a broadcast highlight caption. "
                        "Describe only supplied actions: never invent a player, event, "
                        "outcome, score, crowd reaction, or timestamp."
                    ),
                },
                {"role": "user", "content": _commentary_input(response, submission)},
            ],
            text_format=GeneratedCommentary,
        ).output_parsed
        if generated is None:
            return None

        # Ignore duplicate or unknown IDs and restore authoritative scheduler
        # timing. This is the trust boundary between prose and game mechanics.
        seen: set[str] = set()
        cues = []
        for item in generated.phases:
            phase = phase_by_id.get(item.phase_id)
            if phase is None or item.phase_id in seen:
                continue
            seen.add(item.phase_id)
            cues.append(
                CommentaryCue(
                    id=f"commentary-{len(cues) + 1}",
                    phase_id=phase.id,
                    start_time=phase.start_time,
                    end_time=phase.end_time,
                    text=item.text,
                )
            )
        if not cues:
            return None
        track = CommentaryTrack(
            title=generated.title,
            summary=generated.summary,
            cues=tuple(sorted(cues, key=lambda cue: cue.start_time)),
        )
        return track
    except Exception:
        logger.exception("Commentary generation failed")
        return None
