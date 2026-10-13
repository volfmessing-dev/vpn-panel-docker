from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class NodeRole(StrEnum):
    mikrotik = "mikrotik"
    ru_cloud = "ru_cloud"
    amnezia_exit = "amnezia_exit"


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    role: Mapped[NodeRole] = mapped_column(Enum(NodeRole, name="node_role"), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_user: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
