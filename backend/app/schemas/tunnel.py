from datetime import datetime

from pydantic import BaseModel, Field

from app.models.tunnel import TunnelType


class TunnelBase(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    type: TunnelType = TunnelType.wireguard
    source_node_id: int
    target_node_id: int
    tunnel_cidr: str = "10.200.0.0/30"
    listen_port: int = Field(default=51840, ge=1, le=65535)
    lan_cidr: str = "192.168.50.0/24"
    enabled: bool = True


class TunnelCreate(TunnelBase):
    pass


class TunnelUpdate(TunnelBase):
    pass


class TunnelRead(TunnelBase):
    id: int
    source_public_key: str | None = None
    target_public_key: str | None = None
    applied_at: datetime | None = None

    model_config = {"from_attributes": True}


class TunnelPreview(BaseModel):
    tunnel_id: int
    name: str
    type: TunnelType = TunnelType.wireguard
    tunnel_network: str
    source_tunnel_ip: str
    target_tunnel_ip: str
    gateway: str
    endpoint: str
    mikrotik_allowed_ips: str
    ru_cloud_config: str
    mikrotik_config: str
    mikrotik_commands: str
    ru_cloud_config_path: str | None = None
    exit_config: str | None = None
    exit_config_path: str | None = None
    interface_name: str | None = None
    ru_cloud_commands: str | None = None
    exit_commands: str | None = None
    notes: list[str]


class TunnelApplyResult(BaseModel):
    tunnel_id: int
    name: str
    status: str
    message: str
    ru_cloud_config_path: str
    source_public_key: str
    target_public_key: str


class AmneziaWGApplyResult(BaseModel):
    tunnel_id: int
    name: str
    status: str
    message: str
    interface_name: str
    ru_cloud_config_path: str
    exit_config_path: str
    exit_egress_interface: str
    source_public_key: str
    target_public_key: str
