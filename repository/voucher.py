from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from models.Ticket import Ticket
from models.Voucher import Voucher
from schemas.voucher import VoucherResponseItem


def get_voucher_by_id(db: Session, id: str) -> Optional[Voucher]:
    query = (
        select(Voucher).options(selectinload(Voucher.tickets)).where(Voucher.id == id)
    )
    voucher = db.execute(query).scalar()
    return voucher


def insert_voucher(
    db: Session,
    code: str,
    value: int,
    quota: int,
    type: str | None = None,
    email_whitelist: dict | None = None,
    is_active: bool = False,
    ticket_ids: list[str] | None = None,
) -> Voucher:
    tickets = get_tickets_by_ids(db=db, ticket_ids=ticket_ids or [])
    voucher = Voucher(
        code=code,
        value=value,
        quota=quota,
        type=type,
        email_whitelist=email_whitelist,
        is_active=is_active,
        tickets=tickets,
    )
    db.add(voucher)
    db.commit()
    db.refresh(voucher)
    return voucher


def update_voucher(
    db: Session,
    voucher: Voucher,
    code: Optional[str] = None,
    value: Optional[int] = None,
    quota: Optional[int] = None,
    type: Optional[str] = None,
    email_whitelist: Optional[dict] = None,
    is_active: Optional[bool] = None,
    ticket_ids: list[str] | None = None,
    is_commit: bool = True,
) -> Optional[Voucher]:
    tickets = get_tickets_by_ids(db=db, ticket_ids=ticket_ids or [])
    voucher.code = code
    voucher.value = value
    voucher.quota = quota
    voucher.type = type
    voucher.email_whitelist = email_whitelist
    voucher.is_active = is_active
    voucher.tickets = tickets
    if is_commit:
        db.commit()
    return voucher


def update_status(db: Session, voucher_id: str, is_active: bool) -> Optional[Voucher]:
    query = select(Voucher).where(Voucher.id == voucher_id)
    voucher = db.execute(query).scalars().first()
    if voucher:
        voucher.is_active = is_active
        db.commit()
        db.refresh(voucher)
    return voucher


def update_whitelist(
    db: Session, voucher_id: str, email_whitelist: dict
) -> Optional[Voucher]:
    query = select(Voucher).where(Voucher.id == voucher_id)
    voucher = db.execute(query).scalars().first()
    if voucher:
        voucher.email_whitelist = email_whitelist
        db.commit()
        db.refresh(voucher)
    return voucher


def update_quota(db: Session, voucher_id: str, quota: int) -> Optional[Voucher]:
    query = select(Voucher).where(Voucher.id == voucher_id)
    voucher = db.execute(query).scalars().first()
    if voucher:
        voucher.quota = quota
        db.commit()
        db.refresh(voucher)
    return voucher


def update_value(db: Session, voucher_id: str, value: int) -> Optional[Voucher]:
    query = select(Voucher).where(Voucher.id == voucher_id)
    voucher = db.execute(query).scalars().first()
    if voucher:
        voucher.value = value
        db.commit()
        db.refresh(voucher)
    return voucher


def update_type_voucher(db: Session, voucher_id: str, type: str) -> Optional[Voucher]:
    query = select(Voucher).where(Voucher.id == voucher_id)
    voucher = db.execute(query).scalars().first()
    if voucher:
        voucher.type = type
        db.commit()
        db.refresh(voucher)
    return voucher


def get_vouchers_per_page(
    db: Session,
    page: int,
    page_size: int,
    search: Optional[str] = None,
    all: bool = False,
) -> dict:
    offset = (page - 1) * page_size

    stmt = select(Voucher)

    if search:
        stmt = stmt.where(
            Voucher.code.ilike(f"%{search}%"),
        )

    total_count = db.scalar(select(func.count()).select_from(stmt.subquery()))

    if all is False:
        stmt = stmt.offset(offset).limit(page_size)

    results = db.scalars(stmt).all()
    results_schema = [VoucherResponseItem.model_validate(r) for r in results]
    if all:
        page_count = 1 if total_count else 0
    else:
        page_count = (total_count + page_size - 1) // page_size if total_count else 0

    return {
        "page": page,
        "page_size": page_size,
        "count": total_count,
        "page_count": page_count,
        "results": results_schema,
    }


def get_voucher_by_code(db: Session, code: str) -> Optional[Voucher]:
    stmt = (
        select(Voucher)
        .options(selectinload(Voucher.tickets))
        .where(func.upper(Voucher.code) == code.strip().upper())
    )
    voucher = db.execute(stmt).scalar()
    return voucher


def validate_and_use_voucher(
    db: Session,
    code: str,
    user_email: str,
    ticket_id: str | None = None,
) -> tuple[Optional[Voucher], Optional[str]]:
    # Lock the voucher row for update to prevent race conditions
    stmt = (
        select(Voucher)
        .options(selectinload(Voucher.tickets))
        .where(func.upper(Voucher.code) == code.strip().upper())
        .with_for_update()
    )
    voucher = db.execute(stmt).scalar()

    if not voucher:
        return None, "Invalid voucher code."

    if not voucher.is_active:
        return None, "Voucher is no longer valid."

    if voucher.quota <= 0:
        return None, "Voucher quota has been exhausted."

    if voucher.email_whitelist:
        whitelist = voucher.email_whitelist.get("emails", [])

        whitelist_normalized = {
            e.strip().lower() for e in whitelist if isinstance(e, str)
        }
        user_email_normalized = user_email.strip().lower()
        if whitelist_normalized and user_email_normalized not in whitelist_normalized:
            return None, "You are not authorized to use this voucher."

    if not voucher_can_be_used_for_ticket(voucher=voucher, ticket_id=ticket_id):
        return None, "Voucher cannot be used for this ticket."

    voucher.quota -= 1
    db.flush()

    return voucher, None


def get_tickets_by_ids(db: Session, ticket_ids: list[str]) -> list[Ticket]:
    unique_ticket_ids = list(dict.fromkeys(ticket_ids))
    if not unique_ticket_ids:
        return []

    tickets = db.scalars(select(Ticket).where(Ticket.id.in_(unique_ticket_ids))).all()
    if len(tickets) != len(unique_ticket_ids):
        raise ValueError("One or more tickets not found")
    return tickets


def voucher_can_be_used_for_ticket(voucher: Voucher, ticket_id: str | None) -> bool:
    return (
        ticket_id is None
        or not voucher.tickets
        or any(str(ticket.id) == str(ticket_id) for ticket in voucher.tickets)
    )
