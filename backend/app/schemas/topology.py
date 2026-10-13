from pydantic import BaseModel


class TopologyLink(BaseModel):
    source: str
    target: str
    type: str
    status: str


class Topology(BaseModel):
    nodes: list[dict[str, str]]
    links: list[TopologyLink]
