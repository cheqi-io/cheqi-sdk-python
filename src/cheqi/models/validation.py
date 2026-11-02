"""Receipt validation findings returned to the issuing integration."""

from __future__ import annotations

from typing import Literal, Tuple

from pydantic import BaseModel, ConfigDict, Field


class InvoiceValidationIssue(BaseModel):
    """One validation rule, its field path and an explanation."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, strict=True, extra="forbid")
    rule_id: str = Field(alias="ruleId", min_length=1)
    path: str
    message: str = Field(min_length=1)


class InvoiceValidationReport(BaseModel):
    """All detected payload issues; final document validation runs in the wallet."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, strict=True, extra="forbid")
    profile: Literal["EN16931_CORE_2017_V1"]
    valid: bool
    complete_document: Literal[False] = Field(alias="completeDocument")
    issues: Tuple[InvoiceValidationIssue, ...]
