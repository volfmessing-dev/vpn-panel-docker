"""add vpn users

Revision ID: 0004_vpn_users
Revises: 0003_tunnel_keys
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_vpn_users"
down_revision = "0003_tunnel_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vpn_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=False),
        sa.Column("private_key", sa.Text(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_ip"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_vpn_users_id"), "vpn_users", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_vpn_users_id"), table_name="vpn_users")
    op.drop_table("vpn_users")
