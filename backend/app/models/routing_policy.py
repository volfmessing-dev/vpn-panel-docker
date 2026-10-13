from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RoutingPolicySource(StrEnum):
    wg_users_bypass = "wg_users_bypass"
    wg_users_default = "wg_users_default"
    wg_mikrotik = "wg_mikrotik"


class RoutingPolicyTarget(StrEnum):
    tunnel = "tunnel"
    direct = "direct"


class RoutingPolicy(Base):
    __tablename__ = "routing_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[RoutingPolicySource] = mapped_column(
        Enum(RoutingPolicySource, name="routing_policy_source"),
        unique=True,
        nullable=False,
    )
    target: Mapped[RoutingPolicyTarget] = mapped_column(
        Enum(RoutingPolicyTarget, name="routing_policy_target"),
        nullable=False,
    )
    target_tunnel_id: Mapped[int | None] = mapped_column(ForeignKey("tunnels.id"), nullable=True)
    direct_interface: Mapped[str | None] = mapped_column(String(32), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
