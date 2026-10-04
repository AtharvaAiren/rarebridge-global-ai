"""Request models. Responses are plain dicts shaped by the frozen contract and
the fixtures in handoffs/fixtures/ (additive optional fields only)."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    assessment_id: str = Field(min_length=1)
    withdrawn_source_ids: list[str] = Field(default_factory=list)


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_id: str = Field(min_length=1)
    title: str
    url: str
    published_on: Optional[str] = None
    text: str = Field(min_length=1)


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    assessment_id: str = Field(min_length=1)
    withdrawn_source_ids: list[str] = Field(default_factory=list)


class DiscoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disease_id: str = Field(min_length=1, max_length=300)
    goal_id: str = Field(default="natural_history", min_length=1, max_length=80)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessment_id: str = Field(min_length=1, max_length=300)
    withdrawn_source_ids: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(default_factory=list, max_length=25)
    question: str = Field(min_length=1, max_length=1_200)
    mode: Literal["patient", "expert"] = "patient"
