"""Base model and custom types for Cheqi SDK."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic.functional_serializers import PlainSerializer
from typing_extensions import Annotated


def _strip_trailing_zeros(v: Decimal) -> str:
    """Strip trailing zeros from a Decimal for JSON serialization.

    Matches Java BigDecimal behavior where 100.00 serializes as "100"
    and 21.50 serializes as "21.5".
    """
    normalized = v.normalize()
    # Avoid scientific notation for small numbers
    if normalized == normalized.to_integral_value():
        return str(int(normalized))
    return str(normalized)


CheqiDecimal = Annotated[Decimal, PlainSerializer(_strip_trailing_zeros, when_used="json")]


class CheqiBaseModel(BaseModel):
    """Base model for all Cheqi SDK models.

    Features:
    - camelCase JSON aliases (Python uses snake_case, JSON uses camelCase)
    - Immutable (frozen) models
    - None values excluded from serialization
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        frozen=True,
    )

    def to_json(self) -> str:
        """Serialize to JSON string with camelCase keys, excluding None values."""
        return self.model_dump_json(exclude_none=True, by_alias=True)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict with camelCase keys, excluding None values."""
        return self.model_dump(exclude_none=True, by_alias=True, mode="json")
