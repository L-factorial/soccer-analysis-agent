"""Internal structured output models used to constrain model-generated prose."""

from pydantic import BaseModel, ConfigDict, Field


class CommentaryPhaseInput(BaseModel):
    """Minimal validated timing boundary for a serialized selected phase."""
    model_config = ConfigDict(extra="allow")

    id: str
    start_time: float = Field(alias="startTime", ge=0)
    end_time: float = Field(alias="endTime", ge=0)
    duration: float = Field(gt=0)


class CommentaryDiagnosticsInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    selected_phases: tuple[CommentaryPhaseInput, ...] = Field(
        default=(), alias="selectedPhases"
    )


class CommentarySimulationInput(BaseModel):
    """Read-only subset of the camelCase animation response returned by the API."""
    duration: float = Field(ge=0)
    events: tuple[dict, ...]
    diagnostics: CommentaryDiagnosticsInput | None = None


class GeneratedPhaseCommentary(BaseModel):
    phase_id: str = Field(description="An exact phase ID from the supplied plan")
    text: str = Field(
        min_length=1,
        max_length=240,
        description="One short, energetic but tactically accurate sentence",
    )


class GeneratedCommentary(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=300)
    phases: tuple[GeneratedPhaseCommentary, ...]
