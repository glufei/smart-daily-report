from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from .schemas import ReportView

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


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


SafeErrorCode = Literal[
    "non_workday", "all_sources_failed", "source_auth_failed", "source_unavailable",
    "source_payload_invalid", "report_write_failed", "delivery_rejected",
    "delivery_partial", "delivery_unknown", "operation_interrupted", "internal_error",
]


class SourceOutcome(OperationModel):
    status: Literal["pending", "success", "failure", "disabled"]
    error_code: SafeErrorCode | None


class DeliveryOutcome(OperationModel):
    status: Literal["not_requested", "pending", "accepted", "rejected", "partial_failure", "unknown"]
    attempts: Annotated[int, Field(ge=0)]
    error_code: SafeErrorCode | None

    @model_validator(mode="after")
    def not_requested_has_no_attempts(self):
        if self.status == "not_requested" and self.attempts != 0:
            raise ValueError("An unrequested channel has no attempts")
        return self


OperationId = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]


class SourceOutcomes(OperationModel):
    github_commits: SourceOutcome | None
    lark_tasks: SourceOutcome | None
    lark_messages: SourceOutcome | None


class DeliveryOutcomes(OperationModel):
    email: DeliveryOutcome
    lark: DeliveryOutcome


class OperationView(GenerationRequest):
    operation_id: OperationId
    request_id: OperationId
    kind: Literal["generation", "delivery"]
    status: Literal["running", "succeeded", "partial_failure", "failed", "skipped", "unknown", "interrupted"]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    report_revision: Revision | None
    sources: SourceOutcomes
    deliveries: DeliveryOutcomes
    error_code: SafeErrorCode | None

    @model_validator(mode="after")
    def source_evidence_matches_kind(self):
        values = list(self.sources.model_dump().values())
        if self.kind == "generation" and any(value is None for value in values):
            raise ValueError("Generation requires all source states")
        if self.kind == "delivery" and any(value is not None for value in values):
            raise ValueError("Delivery does not collect sources")
        return self


class TargetView(OperationModel):
    enabled: bool
    label: str
    previous: DeliveryOutcome | None


class TargetViews(OperationModel):
    email: TargetView
    lark: TargetView


class PreviewView(OperationModel):
    report: ReportView
    report_revision: Revision
    sources: SourceOutcomes | None
    targets: TargetViews
