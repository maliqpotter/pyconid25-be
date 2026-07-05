"""speaker schedule many to many

Revision ID: c4f1a92b7d30
Revises: 80a7628ad31b
Create Date: 2026-06-21 12:00:00.000000

Change speaker schedule relationship from one-to-many (schedule.speaker_id)
to many-to-many through the ``speaker_schedule`` junction table.

Each junction row stores:
    speaker_id (composite PK, FK -> speaker.id)
    schedule_id (composite PK, FK -> schedule.id)
    - type ("Main Speaker" / "Co Speaker" / etc.)
    "order" display order of the speaker on the schedule (consistent frontend)

Existing ``schedule.speaker_id`` data is migrated to the junction
with ``type='Main Speaker'`` and ``"order"=1`` before dropping the column,
so existing data remains safe.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4f1a92b7d30"
down_revision: Union[str, None] = "80a7628ad31b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create junction table speaker_schedule (composite PK)
    op.create_table(
        "speaker_schedule",
        sa.Column("speaker_id", sa.UUID(), nullable=False),
        sa.Column("schedule_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["schedule_id"],
            ["public.schedule.id"],
        ),
        sa.ForeignKeyConstraint(
            ["speaker_id"],
            ["public.speaker.id"],
        ),
        sa.PrimaryKeyConstraint("speaker_id", "schedule_id"),
        sa.UniqueConstraint("schedule_id", "order", name="uq_schedule_speaker_order"),
        schema="public",
    )
    op.create_index(
        op.f("ix_public_speaker_schedule_schedule_id"),
        "speaker_schedule",
        ["schedule_id"],
        unique=False,
        schema="public",
    )
    op.create_index(
        op.f("ix_public_speaker_schedule_speaker_id"),
        "speaker_schedule",
        ["speaker_id"],
        unique=False,
        schema="public",
    )

    # 2. Migrate existing speaker_id data from schedule to junction.
    #    Each schedule that already has a speaker_id gets one junction row
    #    with type='Main Speaker' and "order"=1.
    op.execute(
        sa.text(
            """
            INSERT INTO public.speaker_schedule
                (speaker_id, schedule_id, type, "order", created_at, updated_at)
            SELECT
                speaker_id,
                id,
                'Main Speaker',
                1,
                NOW(),
                NOW()
            FROM public.schedule
            WHERE speaker_id IS NOT NULL
            """
        )
    )

    # 3. Drop speaker_id column (and its index) from schedule
    op.drop_index(
        op.f("ix_public_schedule_speaker_id"),
        table_name="schedule",
        schema="public",
    )
    op.drop_column("schedule", "speaker_id", schema="public")


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Restore speaker_id column in schedule (nullable)
    op.add_column(
        "schedule",
        sa.Column("speaker_id", sa.UUID(), nullable=True),
        schema="public",
    )
    op.create_index(
        op.f("ix_public_schedule_speaker_id"),
        "schedule",
        ["speaker_id"],
        unique=False,
        schema="public",
    )
    op.create_foreign_key(
        "schedule_speaker_id_fkey",
        "schedule",
        "speaker",
        ["speaker_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
    )

    # 2. Restore speaker_id from junction (take the row with the smallest "order" per
    #    schedule as the primary speaker).
    op.execute(
        sa.text(
            """
            UPDATE public.schedule AS s
            SET speaker_id = ss.speaker_id
            FROM (
                SELECT DISTINCT ON (schedule_id) schedule_id, speaker_id
                FROM public.speaker_schedule
                ORDER BY schedule_id, "order" ASC
            ) AS ss
            WHERE s.id = ss.schedule_id
            """
        )
    )

    # 3. Drop junction table
    op.drop_index(
        op.f("ix_public_speaker_schedule_speaker_id"),
        table_name="speaker_schedule",
        schema="public",
    )
    op.drop_index(
        op.f("ix_public_speaker_schedule_schedule_id"),
        table_name="speaker_schedule",
        schema="public",
    )
    op.drop_table("speaker_schedule", schema="public")
