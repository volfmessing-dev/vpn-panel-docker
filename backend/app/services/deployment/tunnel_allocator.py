import ipaddress
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node, NodeRole
from app.models.tunnel import Tunnel, TunnelType

WG_POOL = ipaddress.ip_network("10.230.0.0/16")
AWG_POOL = ipaddress.ip_network("10.240.0.0/16")
WG_PORT_BASE = 51840
AWG_PORT_BASE = 9440


def create_ru_cloud_uplink(node: Node, tunnel_type: TunnelType, db: Session) -> Tunnel:
    ru_cloud = db.scalar(select(Node).where(Node.role == NodeRole.ru_cloud).order_by(Node.id))
    if not ru_cloud:
        raise ValueError("RU_Cloud node not found")
    if node.id == ru_cloud.id:
        raise ValueError("RU_Cloud does not need an uplink to itself")

    source_node_id, target_node_id = _direction(node, ru_cloud)
    tunnel = Tunnel(
        name=_next_tunnel_name(node.name, tunnel_type, db),
        type=tunnel_type,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        tunnel_cidr=str(_next_tunnel_network(tunnel_type, db)),
        listen_port=_next_listen_port(tunnel_type, db),
        lan_cidr="192.168.50.0/24" if node.role == NodeRole.mikrotik else "0.0.0.0/0",
        enabled=True,
    )
    db.add(tunnel)
    db.commit()
    db.refresh(tunnel)
    return tunnel


def _direction(node: Node, ru_cloud: Node) -> tuple[int, int]:
    if node.role == NodeRole.amnezia_exit:
        return ru_cloud.id, node.id
    return node.id, ru_cloud.id


def _next_tunnel_network(tunnel_type: TunnelType, db: Session) -> ipaddress.IPv4Network:
    pool = AWG_POOL if tunnel_type == TunnelType.amneziawg else WG_POOL
    used = {
        ipaddress.ip_network(cidr, strict=False)
        for cidr in db.scalars(select(Tunnel.tunnel_cidr)).all()
    }
    for network in pool.subnets(new_prefix=30):
        if network not in used:
            return network
    raise ValueError(f"No free /30 networks in {pool}")


def _next_listen_port(tunnel_type: TunnelType, db: Session) -> int:
    base = AWG_PORT_BASE if tunnel_type == TunnelType.amneziawg else WG_PORT_BASE
    used = set(db.scalars(select(Tunnel.listen_port)).all())
    port = base
    while port in used:
        port += 1
    if port > 65535:
        raise ValueError("No free listen ports")
    return port


def _next_tunnel_name(node_name: str, tunnel_type: TunnelType, db: Session) -> str:
    prefix = "awg" if tunnel_type == TunnelType.amneziawg else "wg"
    base = f"{prefix}-{_slug(node_name)}"
    existing = set(db.scalars(select(Tunnel.name)).all())
    if base not in existing:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing:
        suffix += 1
    return f"{base}-{suffix}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "node"
