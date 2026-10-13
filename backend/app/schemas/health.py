from datetime import datetime
from pydantic import BaseModel


class NodeHealth(BaseModel):
    checked_at: datetime | None = None
    node_id: int
    name: str
    status: str
    check: str
    message: str
    latency_ms: int | None = None
