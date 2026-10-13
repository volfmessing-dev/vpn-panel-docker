"""add routing policies

Revision ID: 0005_routing_policies
Revises: 0004_vpn_users
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_routing_policies"
down_revision = "0004_vpn_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    policy_source = sa.Enum(
        "wg_users_bypass",
        "wg_users_default",
        "wg_mikrotik",
        name="routing_policy_source",
    )
    policy_target = sa.Enum("tunnel", "direct", name="routing_policy_target")

    op.create_table(
        "routing_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", policy_source, nullable=False),
        sa.Column("target", policy_target, nullable=False),
        sa.Column("target_tunnel_id", sa.Integer(), nullable=True),
        sa.Column("direct_interface", sa.String(length=32), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["target_tunnel_id"], ["tunnels.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source"),
    )
    op.create_index(op.f("ix_routing_policies_id"), "routing_policies", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_routing_policies_id"), table_name="routing_policies")
    op.drop_table("routing_policies")
    sa.Enum(name="routing_policy_target").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="routing_policy_source").drop(op.get_bind(), checkfirst=True)
