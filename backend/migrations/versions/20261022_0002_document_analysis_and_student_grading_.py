"""document analysis and student grading scales

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22 16:58:33.661173
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("analysis", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )

    with op.batch_alter_table("grading_scales", schema=None) as batch_op:
        batch_op.add_column(sa.Column("student_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("template_key", sa.String(length=40), nullable=True))
        batch_op.drop_constraint(batch_op.f("uq_grading_scales_name"), type_="unique")
        batch_op.create_index(
            batch_op.f("ix_grading_scales_student_id"), ["student_id"], unique=False
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_grading_scales_template_key"), ["template_key"]
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_grading_scales_student_id_students"),
            "students",
            ["student_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("grading_scales", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_grading_scales_student_id_students"), type_="foreignkey"
        )
        batch_op.drop_constraint(batch_op.f("uq_grading_scales_template_key"), type_="unique")
        batch_op.drop_index(batch_op.f("ix_grading_scales_student_id"))
        batch_op.create_unique_constraint(batch_op.f("uq_grading_scales_name"), ["name"])
        batch_op.drop_column("template_key")
        batch_op.drop_column("student_id")

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_column("analysis")
