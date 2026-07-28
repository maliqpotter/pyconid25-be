"""add voucher ticket table

Revision ID: 2f45e9d7a8c1
Revises: b7c9d8e1f2a3
Create Date: 2026-07-25 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2f45e9d7a8c1"
down_revision: Union[str, None] = "b7c9d8e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voucher_ticket",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("voucher_id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["public.ticket.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["voucher_id"], ["public.voucher.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("voucher_id", "ticket_id"),
        schema="public",
    )
    op.create_index(
        op.f("ix_public_voucher_ticket_id"),
        "voucher_ticket",
        ["id"],
        unique=False,
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_public_voucher_ticket_id"),
        table_name="voucher_ticket",
        schema="public",
    )
    op.drop_table("voucher_ticket", schema="public")
