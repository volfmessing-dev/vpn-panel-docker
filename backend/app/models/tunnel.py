from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TunnelType(StrEnum):
    wireguard = "wireguard"
    amneziawg = "amneziawg"


class Tunnel(Base):
    __tablename__ = "tunnels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    type: Mapped[TunnelType] = mapped_column(Enum(TunnelType, name="tunnel_type"), nullable=False)
    source_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False)
    target_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False)
    tunnel_cidr: Mapped[str] = mapped_column(String(64), nullable=False)
    listen_port: Mapped[int] = mapped_column(Integer, default=51820, nullable=False)
    lan_cidr: Mapped[str] = mapped_column(String(64), default="192.168.50.0/24", nullable=False)
    source_private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
