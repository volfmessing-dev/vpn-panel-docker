"""add tunnels

Revision ID: 0002_tunnels
Revises: 0001_initial
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_tunnels"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tunnel_type = sa.Enum("wireguard", "amneziawg", name="tunnel_type")
    op.create_table(
        "tunnels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("type", tunnel_type, nullable=False),
        sa.Column("source_node_id", sa.Integer(), nullable=False),
        sa.Column("target_node_id", sa.Integer(), nullable=False),
        sa.Column("tunnel_cidr", sa.String(length=64), nullable=False),
        sa.Column("listen_port", sa.Integer(), nullable=False),
        sa.Column("lan_cidr", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["source_node_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["target_node_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_tunnels_id"), "tunnels", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tunnels_id"), table_name="tunnels")
    op.drop_table("tunnels")
    sa.Enum(name="tunnel_type").drop(op.get_bind(), checkfirst=True)
