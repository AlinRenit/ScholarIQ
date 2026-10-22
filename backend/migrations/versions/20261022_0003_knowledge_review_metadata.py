"""knowledge review metadata

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22 17:34:58.771915
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("concepts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("reviewed_on", sa.Date(), nullable=True))

    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("reviewed_on", sa.Date(), nullable=True))

    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("reviewed_on", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.drop_column("reviewed_on")
        batch_op.drop_column("reviewed_by")

    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.drop_column("reviewed_on")
        batch_op.drop_column("reviewed_by")

    with op.batch_alter_table("concepts", schema=None) as batch_op:
        batch_op.drop_column("reviewed_on")
        batch_op.drop_column("reviewed_by")
