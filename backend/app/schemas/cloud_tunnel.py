from pydantic import BaseModel


class CloudTunnelPeer(BaseModel):
    public_key: str
    endpoint: str | None = None
    allowed_ips: list[str]
    latest_handshake: int | None = None
    transfer_rx: int | None = None
    transfer_tx: int | None = None
    persistent_keepalive: str | None = None


class CloudTunnelInterface(BaseModel):
    name: str
    display_name: str
    location: str | None = None
    kind: str
    public_key: str | None = None
    listen_port: int | None = None
    fwmark: str | None = None
    addresses: list[str]
    flags: list[str]
    operstate: str | None = None
    mtu: int | None = None
    routes: list[str]
    peers: list[CloudTunnelPeer]


class CloudTunnelSnapshot(BaseModel):
    node_id: int
    node_name: str
    host: str
    status: str
    interfaces: list[CloudTunnelInterface]
    rules: list[str]
    error: str | None = None
