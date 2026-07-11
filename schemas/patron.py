from enum import Enum
from typing import Sequence
from pydantic import BaseModel

from models.Patron import Patron


class PatronTier(str, Enum):
    ULTIMATE = "ultimate"
    PLATINUM = "platinum"
    GOLD = "gold"
    SILVER = "silver"


class PatronResponseItem(BaseModel):
    id: str
    name: str
    tier: str


class PatronListResponse(BaseModel):
    results: list[PatronResponseItem]


def patron_response_item_from_model(patron: Patron) -> PatronResponseItem:
    return PatronResponseItem(
        id=str(patron.id),
        name=patron.name,
        tier=patron.tier,
    )


def patron_list_response_from_models(patrons: Sequence[Patron]) -> PatronListResponse:
    return PatronListResponse(
        results=[patron_response_item_from_model(patron) for patron in patrons]
    )
