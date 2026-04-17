"""
Phase 5.12: Shared ExplainEntry model.
Re-exported by app.models.policy_simulation for backward-compatible imports.
"""
from pydantic import BaseModel, Field


class ExplainEntry(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)
