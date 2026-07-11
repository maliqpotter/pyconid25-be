from typing import Sequence
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from core.helper import get_current_time_in_timezone
from models.Patron import Patron
from settings import TZ


def get_patrons(db: Session) -> Sequence[Patron]:
    tier_order = case(
        (Patron.tier == "ultimate", 1),
        (Patron.tier == "platinum", 2),
        (Patron.tier == "gold", 3),
        (Patron.tier == "silver", 4),
        else_=5,
    )
    stmt = (
        select(Patron)
        .where(Patron.deleted_at.is_(None))
        .order_by(tier_order, Patron.name)
    )
    return db.scalars(stmt).all()


def get_patron_by_id(db: Session, id: str) -> Patron | None:
    stmt = select(Patron).where(Patron.id == id, Patron.deleted_at.is_(None))
    return db.execute(stmt).scalar()


def insert_patron(
    db: Session,
    name: str,
    tier: str,
    image: str | None = None,
) -> Patron:
    current_datetime = get_current_time_in_timezone(TZ)
    patron = Patron(
        name=name,
        tier=tier,
        image=image,
        created_at=current_datetime,
        updated_at=current_datetime,
    )
    db.add(patron)
    db.commit()
    db.refresh(patron)
    return patron


def update_patron(
    db: Session,
    patron: Patron,
    name: str,
    tier: str,
    image: str | None = None,
) -> Patron:
    patron.name = name
    patron.tier = tier
    if image is not None:
        patron.image = image
    patron.updated_at = get_current_time_in_timezone(TZ)
    db.commit()
    db.refresh(patron)
    return patron


def delete_patron(db: Session, patron: Patron) -> None:
    patron.deleted_at = get_current_time_in_timezone(TZ)
    db.commit()
