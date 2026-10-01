from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OperationModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class GenerationRequest(OperationModel):
    report_date: date

    @field_validator("report_date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        if isinstance(value, str):
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                raise ValueError("Invalid calendar date")
            return date.fromisoformat(value)
        if type(value) is not date:
            raise ValueError("Invalid calendar date")
        return value


Revision = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DeliveryRequest(GenerationRequest):
    report_revision: Revision
    channels: list[Literal["email", "lark"]]

    @field_validator("channels")
    @classmethod
    def canonical_channels(cls, value):
        if not value or len(set(value)) != len(value):
            raise ValueError("Select distinct channels")
        return sorted(value)


class SourceOutcome(OperationModel):
    status: Literal["pending", "success", "failure", "disabled"]
    error_code: str | None


class DeliveryOutcome(OperationModel):
    status: Literal["not_requested", "pending", "accepted", "rejected", "partial_failure", "unknown"]
    attempts: Annotated[int, Field(ge=0)]
    error_code: str | None

    @model_validator(mode="after")
    def not_requested_has_no_attempts(self):
        if self.status == "not_requested" and self.attempts != 0:
            raise ValueError("An unrequested channel has no attempts")
        return self
