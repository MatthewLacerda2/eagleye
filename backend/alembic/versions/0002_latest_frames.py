"""latest frames: quiet frames can be dropped; cameras no longer track a sent path

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("observations", "frame_path", existing_type=sa.Text(), nullable=True)
    op.drop_column("cameras", "last_sent_frame_path")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("cameras", sa.Column("last_sent_frame_path", sa.Text(), nullable=True))
    op.execute("UPDATE observations SET frame_path = '' WHERE frame_path IS NULL")
    op.alter_column("observations", "frame_path", existing_type=sa.Text(), nullable=False)
