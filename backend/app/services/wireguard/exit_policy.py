from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.tunnel import Tunnel, TunnelType

EXIT_TABLE = "vpn_panel_exit"
FALLBACK_EXIT_INTERFACE = "awg1"
DIRECT_INTERFACE = "enp3s0"


def available_exit_interface(db: Session, excluding_node_id: int | None = None) -> str:
    tunnel = available_exit_tunnel(db, excluding_node_id)
    if not tunnel:
        return FALLBACK_EXIT_INTERFACE
    target = db.get(Node, tunnel.target_node_id)
    return exit_interface_name(tunnel, target.name if target else tunnel.name)


def available_exit_tunnel(db: Session, excluding_node_id: int | None = None) -> Tunnel | None:
    row = db.execute(
        select(Tunnel)
        .where(Tunnel.type == TunnelType.amneziawg)
        .where(Tunnel.enabled.is_(True))
        .where(Tunnel.target_node_id != excluding_node_id if excluding_node_id is not None else True)
        .order_by(Tunnel.id)
    ).first()
    if not row:
        return None
    return row[0]


def exit_interface_name(tunnel: Tunnel, node_name: str | None = None) -> str:
    normalized_name = (node_name or tunnel.name).lower()
    if normalized_name == "exit_b":
        return "awg4"
    if normalized_name == "exit_c":
        return "awg3"
    if normalized_name == "exit_a":
        return "awg1"
    if tunnel.name.startswith("awg-"):
        return tunnel.name.replace("-", "_")[:15]
    return f"awg{max(1, tunnel.listen_port - 9439)}"
