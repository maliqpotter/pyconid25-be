import uuid

from sqlalchemy import UUID, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class VoucherTicket(Base):
    __tablename__ = "voucher_ticket"
    __table_args__ = (UniqueConstraint("voucher_id", "ticket_id"),)

    id: Mapped[str] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    voucher_id: Mapped[str] = mapped_column(
        "voucher_id",
        UUID(as_uuid=True),
        ForeignKey("voucher.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticket_id: Mapped[str] = mapped_column(
        "ticket_id",
        UUID(as_uuid=True),
        ForeignKey("ticket.id", ondelete="CASCADE"),
        nullable=False,
    )
