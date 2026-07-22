"""Base model and custom types for Cheqi SDK."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Union

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic.functional_serializers import PlainSerializer
from typing_extensions import Annotated


def _decimal_to_json_number(v: Decimal) -> Union[int, float]:
    """Serialize a Decimal as a JSON number with no insignificant zeros.

    Java's shared ObjectMapper calls ``JsonGenerator.writeNumber`` after
    stripping trailing zeros. Returning a string here would instead produce
    quoted JSON (``"21.5"``), which Swift's ``Decimal`` decoder rejects.
    """
    normalized = v.normalize()
    if normalized == normalized.to_integral_value():
        return int(normalized)
    return float(normalized)


CheqiDecimal = Annotated[
    Decimal,
    PlainSerializer(
        _decimal_to_json_number,
        return_type=Union[int, float],
        when_used="json",
    ),
]


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
