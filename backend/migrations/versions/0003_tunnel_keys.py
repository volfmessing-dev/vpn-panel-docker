"""add tunnel keys

Revision ID: 0003_tunnel_keys
Revises: 0002_tunnels
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_tunnel_keys"
down_revision = "0002_tunnels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tunnels", sa.Column("source_private_key", sa.Text(), nullable=True))
    op.add_column("tunnels", sa.Column("source_public_key", sa.Text(), nullable=True))
    op.add_column("tunnels", sa.Column("target_private_key", sa.Text(), nullable=True))
    op.add_column("tunnels", sa.Column("target_public_key", sa.Text(), nullable=True))
    op.add_column("tunnels", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tunnels", "applied_at")
    op.drop_column("tunnels", "target_public_key")
    op.drop_column("tunnels", "target_private_key")
    op.drop_column("tunnels", "source_public_key")
    op.drop_column("tunnels", "source_private_key")
