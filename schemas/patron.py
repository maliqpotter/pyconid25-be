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


class PatronListResponseItem(PatronResponseItem):
    has_image: bool


class PatronListResponse(BaseModel):
    results: list[PatronListResponseItem]


def patron_response_item_from_model(patron: Patron) -> PatronResponseItem:
    return PatronResponseItem(
        id=str(patron.id),
        name=patron.name,
        tier=patron.tier,
    )


def patron_list_response_from_models(patrons: Sequence[Patron]) -> PatronListResponse:
    return PatronListResponse(
        results=[
            PatronListResponseItem(
                id=str(patron.id),
                name=patron.name,
                tier=patron.tier,
                has_image=patron.image is not None,
            )
            for patron in patrons
        ]
    )
