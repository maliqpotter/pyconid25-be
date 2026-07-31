from typing import List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.City import City
from models.Country import Country
from models.Payment import Payment, PaymentStatus
from models.State import State
from models.User import User


def _paid_user_base_filters():
    return [
        Payment.status == PaymentStatus.PAID.value,
        User.deleted_at.is_(None),
    ]


def get_registered_users_count_by_city(db: Session) -> List[dict]:
    stmt = (
        select(
            City.id,
            City.name,
            func.count(func.distinct(User.id)).label("count"),
        )
        .select_from(Payment)
        .join(User, User.id == Payment.user_id)
        .join(City, City.id == User.city_id)
        .where(*_paid_user_base_filters(), User.city_id.is_not(None))
        .group_by(City.id, City.name)
        .order_by(func.count(func.distinct(User.id)).desc(), City.name.asc())
    )
    rows = db.execute(stmt).all()
    return [
        {
            "city": {"id": row.id, "name": row.name},
            "count": row.count,
        }
        for row in rows
    ]


def get_registered_users_count_by_state(db: Session) -> List[dict]:
    stmt = (
        select(
            State.id,
            State.name,
            func.count(func.distinct(User.id)).label("count"),
        )
        .select_from(Payment)
        .join(User, User.id == Payment.user_id)
        .join(State, State.id == User.state_id)
        .where(*_paid_user_base_filters(), User.state_id.is_not(None))
        .group_by(State.id, State.name)
        .order_by(func.count(func.distinct(User.id)).desc(), State.name.asc())
    )
    rows = db.execute(stmt).all()
    return [
        {
            "state": {"id": row.id, "name": row.name},
            "count": row.count,
        }
        for row in rows
    ]


def get_registered_users_count_by_country(db: Session) -> List[dict]:
    stmt = (
        select(
            Country.id,
            Country.name,
            func.count(func.distinct(User.id)).label("count"),
        )
        .select_from(Payment)
        .join(User, User.id == Payment.user_id)
        .join(Country, Country.id == User.country_id)
        .where(*_paid_user_base_filters(), User.country_id.is_not(None))
        .group_by(Country.id, Country.name)
        .order_by(func.count(func.distinct(User.id)).desc(), Country.name.asc())
    )
    rows = db.execute(stmt).all()
    return [
        {
            "country": {"id": row.id, "name": row.name},
            "count": row.count,
        }
        for row in rows
    ]
