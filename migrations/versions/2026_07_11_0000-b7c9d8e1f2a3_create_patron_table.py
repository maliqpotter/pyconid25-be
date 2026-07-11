"""create patron table

Revision ID: b7c9d8e1f2a3
Revises: c4f1a92b7d30
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c9d8e1f2a3"
down_revision: Union[str, None] = "c4f1a92b7d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "patron",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tier", sa.String(length=50), nullable=False),
        sa.Column("image", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="public",
    )
    op.create_index(
        op.f("ix_public_patron_id"), "patron", ["id"], unique=False, schema="public"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_public_patron_id"), table_name="patron", schema="public")
    op.drop_table("patron", schema="public")
