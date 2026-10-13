from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.routing_policy import RoutingPolicy, RoutingPolicySource, RoutingPolicyTarget
from app.models.tunnel import Tunnel, TunnelType
from app.schemas.routing_policy import RoutingPolicyPreview, RoutingPolicyRead, RoutingPolicySnapshot
from app.schemas.tunnel import TunnelRead
from app.services.wireguard.exit_policy import DIRECT_INTERFACE, available_exit_tunnel, exit_interface_name

DEFAULT_PRIORITIES = {
    RoutingPolicySource.wg_users_bypass: 12090,
    RoutingPolicySource.wg_users_default: 12091,
    RoutingPolicySource.wg_mikrotik: 12031,
}


def ensure_default_routing_policies(db: Session) -> list[RoutingPolicy]:
    existing = {policy.source: policy for policy in db.scalars(select(RoutingPolicy)).all()}
    default_tunnel = available_exit_tunnel(db)
    changed = False

    for source in RoutingPolicySource:
        if source in existing:
            continue
        policy = _default_policy(source, default_tunnel)
        db.add(policy)
        existing[source] = policy
        changed = True

    if changed:
        db.commit()
        for policy in existing.values():
            db.refresh(policy)

    return [existing[source] for source in RoutingPolicySource]


def routing_policy_snapshot(db: Session) -> RoutingPolicySnapshot:
    policies = ensure_default_routing_policies(db)
    tunnels = _available_tunnels(db)
    return RoutingPolicySnapshot(
        policies=[_read_policy(policy, db) for policy in policies],
        available_tunnels=[TunnelRead.model_validate(tunnel) for tunnel in tunnels],
    )


def routing_policy_previews(db: Session) -> list[RoutingPolicyPreview]:
    ensure_default_routing_policies(db)
    return [
        _preview_wg_users_bypass(db),
        _preview_wg_users_default(db),
        _preview_wg_mikrotik(db),
    ]


def update_routing_policy(
    source: RoutingPolicySource,
    target: RoutingPolicyTarget,
    target_tunnel_id: int | None,
    direct_interface: str | None,
    enabled: bool,
    db: Session,
) -> RoutingPolicy:
    policies = {policy.source: policy for policy in ensure_default_routing_policies(db)}
    policy = policies[source]

    if target == RoutingPolicyTarget.tunnel:
        tunnel = db.get(Tunnel, target_tunnel_id)
        if not tunnel or tunnel.type != TunnelType.amneziawg:
            raise ValueError("target_tunnel_id must point to an AmneziaWG tunnel")
        if not tunnel.enabled:
            raise ValueError("target tunnel is disabled")
        policy.target_tunnel_id = tunnel.id
        policy.direct_interface = None
    else:
        policy.target_tunnel_id = None
        policy.direct_interface = direct_interface

    policy.target = target
    policy.enabled = enabled
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def resolved_policy_interface(source: RoutingPolicySource, db: Session) -> str:
    policy = {item.source: item for item in ensure_default_routing_policies(db)}[source]
    if not policy.enabled:
        raise ValueError(f"Routing policy {source} is disabled")
    if policy.target == RoutingPolicyTarget.direct:
        return policy.direct_interface or DIRECT_INTERFACE
    tunnel = db.get(Tunnel, policy.target_tunnel_id)
    if not tunnel:
        raise ValueError(f"Routing policy {source} target tunnel not found")
    target_node = db.get(Node, tunnel.target_node_id)
    return exit_interface_name(tunnel, target_node.name if target_node else tunnel.name)


def resolved_policy_interface_or_default(source: RoutingPolicySource, db: Session, default_interface: str) -> str:
    try:
        return resolved_policy_interface(source, db)
    except ValueError:
        return default_interface


def policy_uses_tunnel(source: RoutingPolicySource, db: Session) -> bool:
    policy = {item.source: item for item in ensure_default_routing_policies(db)}[source]
    return policy.enabled and policy.target == RoutingPolicyTarget.tunnel


def _preview_wg_users_bypass(db: Session) -> RoutingPolicyPreview:
    try:
        interface = resolved_policy_interface(RoutingPolicySource.wg_users_bypass, db)
        warnings: list[str] = []
    except ValueError as exc:
        interface = None
        warnings = [str(exc)]
    return RoutingPolicyPreview(
        source=RoutingPolicySource.wg_users_bypass,
        resolved_interface=interface,
        commands=[
            "ip route replace 10.90.0.0/24 dev wg-ru-cloud",
            f"ip route replace default dev {interface or '<unresolved>'} table vpn_panel_exit",
            "ip rule add fwmark 0x77 table vpn_panel_exit priority 12090",
            "iptables -t mangle -I PREROUTING 1 -i wg-ru-cloud -s 10.90.0.0/24 -m set --match-set vpn_panel_bypass_v4 dst -j MARK --set-mark 0x77",
            f"iptables -t nat -A POSTROUTING -s 10.90.0.0/24 -o {interface or '<unresolved>'} -j MASQUERADE",
        ],
        warnings=warnings,
    )


def _preview_wg_users_default(db: Session) -> RoutingPolicyPreview:
    policies = {item.source: item for item in ensure_default_routing_policies(db)}
    policy = policies[RoutingPolicySource.wg_users_default]
    try:
        interface = resolved_policy_interface(RoutingPolicySource.wg_users_default, db)
        warnings: list[str] = []
    except ValueError as exc:
        interface = None
        warnings = [str(exc)]

    commands = [
        f"iptables -t nat -A POSTROUTING -s 10.90.0.0/24 -o {interface or '<unresolved>'} -j MASQUERADE",
    ]
    if policy.enabled and policy.target == RoutingPolicyTarget.tunnel:
        commands.insert(0, "ip rule add from 10.90.0.0/24 table vpn_panel_exit priority 12091")
    else:
        commands.insert(0, "ip rule del from 10.90.0.0/24 table vpn_panel_exit priority 12091")

    return RoutingPolicyPreview(
        source=RoutingPolicySource.wg_users_default,
        resolved_interface=interface,
        commands=commands,
        warnings=warnings,
    )


def _preview_wg_mikrotik(db: Session) -> RoutingPolicyPreview:
    try:
        interface = resolved_policy_interface(RoutingPolicySource.wg_mikrotik, db)
        warnings: list[str] = []
    except ValueError as exc:
        interface = None
        warnings = [str(exc)]
    return RoutingPolicyPreview(
        source=RoutingPolicySource.wg_mikrotik,
        resolved_interface=interface,
        commands=[
            "ip rule add from <mikrotik-lan-cidr> table vpn_panel_exit priority 12031",
            "ip rule add from <mikrotik-wg-ip>/32 table vpn_panel_exit priority 12032",
            f"ip route replace default dev {interface or '<unresolved>'} table vpn_panel_exit",
            f"iptables -t nat -A POSTROUTING -s <mikrotik-lan-cidr> -o {interface or '<unresolved>'} -j MASQUERADE",
        ],
        warnings=warnings,
    )


def _default_policy(source: RoutingPolicySource, default_tunnel: Tunnel | None) -> RoutingPolicy:
    if source == RoutingPolicySource.wg_users_default:
        return RoutingPolicy(
            source=source,
            target=RoutingPolicyTarget.direct,
            target_tunnel_id=None,
            direct_interface=DIRECT_INTERFACE,
            priority=DEFAULT_PRIORITIES[source],
            enabled=True,
        )
    return RoutingPolicy(
        source=source,
        target=RoutingPolicyTarget.tunnel,
        target_tunnel_id=default_tunnel.id if default_tunnel else None,
        direct_interface=None,
        priority=DEFAULT_PRIORITIES[source],
        enabled=default_tunnel is not None,
    )


def _available_tunnels(db: Session) -> list[Tunnel]:
    return list(
        db.scalars(
            select(Tunnel)
            .where(Tunnel.type == TunnelType.amneziawg)
            .where(Tunnel.enabled.is_(True))
            .order_by(Tunnel.id)
        ).all()
    )


def _read_policy(policy: RoutingPolicy, db: Session) -> RoutingPolicyRead:
    tunnel = db.get(Tunnel, policy.target_tunnel_id) if policy.target_tunnel_id else None
    resolved_interface = None
    if policy.enabled:
        try:
            resolved_interface = resolved_policy_interface(policy.source, db)
        except ValueError:
            resolved_interface = None
    return RoutingPolicyRead(
        id=policy.id,
        source=policy.source,
        target=policy.target,
        target_tunnel_id=policy.target_tunnel_id,
        direct_interface=policy.direct_interface,
        enabled=policy.enabled,
        priority=policy.priority,
        applied_at=policy.applied_at,
        target_tunnel=TunnelRead.model_validate(tunnel) if tunnel else None,
        resolved_interface=resolved_interface,
    )
