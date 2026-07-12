import datetime
import uuid
from models import Base
from sqlalchemy import UUID, DateTime, String
from sqlalchemy.orm import mapped_column, Mapped


class Patron(Base):
    __tablename__ = "patron"

    id: Mapped[str] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column("name", String(255), nullable=False)
    tier: Mapped[str] = mapped_column("tier", String(50), nullable=False)
    image: Mapped[str | None] = mapped_column("image", String, nullable=True)

    created_at = mapped_column(
        "created_at",
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
    )
    updated_at = mapped_column(
        "updated_at",
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
    )
