"""
Phase 5.9A: Policy impact simulation API contract.
Pydantic models for request/response; no simulation engine yet.
"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PolicyHorizon = Literal["24h", "30d"]


class EnforcementIntensityIntervention(BaseModel):
    type: Literal["enforcement_intensity"] = "enforcement_intensity"
    pct: Annotated[float, Field(ge=0, le=200)]


class PatrolUnitsIntervention(BaseModel):
    type: Literal["patrol_units"] = "patrol_units"
    from_units: Annotated[int, Field(ge=0, le=50)]
    to_units: Annotated[int, Field(ge=0, le=50)]

    @model_validator(mode="after")
    def to_units_differs_from_from_units(self):
        if self.to_units == self.from_units:
            raise ValueError("to_units must differ from from_units")
        return self


class PeakHourReductionIntervention(BaseModel):
    type: Literal["peak_hour_reduction"] = "peak_hour_reduction"
    pct: Annotated[float, Field(ge=0, le=90)]


Intervention = (
    EnforcementIntensityIntervention
    | PatrolUnitsIntervention
    | PeakHourReductionIntervention
)


class PolicySimulationRequest(BaseModel):
    zones: Annotated[list[str], Field(min_length=1, max_length=10)]
    horizon: PolicyHorizon = "24h"
    anchor_ts: datetime | None = None
    interventions: Annotated[list[Intervention], Field(min_length=1, max_length=5)]

    @field_validator("zones", mode="after")
    @classmethod
    def zones_strip(cls, v: list[str]) -> list[str]:
        return [z.strip() for z in v]

    @model_validator(mode="after")
    def zones_unique_non_empty(self):
        if not all(self.zones):
            raise ValueError("zones must be non-empty after stripping whitespace")
        if len(self.zones) != len(set(self.zones)):
            raise ValueError("zones must be unique")
        return self


# --- Response models ---


class ResponseCacheMeta(BaseModel):
    status: Literal["miss", "hit"]
    key: str | None = None


class PolicySimulationMeta(BaseModel):
    request_id: str
    anchor_ts: str  # ISO datetime string
    response_cache: ResponseCacheMeta


class ZoneTotal(BaseModel):
    zone_id: str
    total: float


class ZoneDelta(BaseModel):
    zone_id: str
    delta: float
    delta_pct: float | None = None


class ExplainEntry(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class BaselineSimulatedBlock(BaseModel):
    horizon: PolicyHorizon
    zones: list[ZoneTotal]
    overall_total: float


class DeltaBlock(BaseModel):
    zones: list[ZoneDelta]
    overall_delta: float
    overall_delta_pct: float | None = None


class PolicySimulationResponse(BaseModel):
    meta: PolicySimulationMeta
    baseline: BaselineSimulatedBlock
    simulated: BaselineSimulatedBlock
    delta: DeltaBlock
    explain: list[ExplainEntry]
