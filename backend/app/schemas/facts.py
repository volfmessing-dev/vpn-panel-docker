from datetime import datetime
from pydantic import BaseModel


class NodeFacts(BaseModel):
    checked_at: datetime | None = None
    node_id: int
    name: str
    status: str
    hostname: str | None = None
    kernel: str | None = None
    os: str | None = None
    public_ip: str | None = None
    ip_forward: str | None = None
    docker: str | None = None
    wireguard: str | None = None
    interfaces: list[str] = []
    routes: list[str] = []
    error: str | None = None
