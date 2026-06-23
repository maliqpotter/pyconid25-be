import datetime

from sqlalchemy import UUID, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base


class SpeakerSchedule(Base):
    """Many-to-many junction between speaker and schedule.

    Stores speaker schedule relation plus metadata per pair:
    - ``order``: speaker display order on schedule (consistent in frontend)
    - ``type``: speaker role, e.g. ``"Main Speaker"`` / ``"Co Speaker"``
    """

    __tablename__ = "speaker_schedule"

    speaker_id: Mapped[str] = mapped_column(
        "speaker_id",
        UUID(as_uuid=True),
        ForeignKey("speaker.id"),
        primary_key=True,
        index=True,
        nullable=False,
    )
    schedule_id: Mapped[str] = mapped_column(
        "schedule_id",
        UUID(as_uuid=True),
        ForeignKey("schedule.id"),
        primary_key=True,
        index=True,
        nullable=False,
    )
    type: Mapped[str] = mapped_column("type", String, nullable=False)
    order: Mapped[int] = mapped_column("order", Integer, nullable=False)
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

    # Relationships
    speaker = relationship("Speaker", back_populates="schedule_speakers")
    schedule = relationship("Schedule", back_populates="speakers")
