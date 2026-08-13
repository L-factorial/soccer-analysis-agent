from pydantic import BaseModel, Field


class Team(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    defended_goal_id: str = Field(min_length=1)
