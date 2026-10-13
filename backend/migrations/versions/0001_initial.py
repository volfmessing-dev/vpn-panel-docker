"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    node_role = sa.Enum("mikrotik", "ru_cloud", "amnezia_exit", name="node_role")
    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("role", node_role, nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("ssh_user", sa.String(length=80), nullable=True),
        sa.Column("ssh_port", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_nodes_id"), "nodes", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_nodes_id"), table_name="nodes")
    op.drop_table("nodes")
    sa.Enum(name="node_role").drop(op.get_bind(), checkfirst=True)
