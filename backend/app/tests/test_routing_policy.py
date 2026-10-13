from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.node import Node, NodeRole
from app.models.routing_policy import RoutingPolicySource, RoutingPolicyTarget
from app.models.tunnel import Tunnel, TunnelType
from app.services.wireguard.routing_policy import (
    resolved_policy_interface,
    routing_policy_previews,
    routing_policy_snapshot,
    update_routing_policy,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_awg_tunnel(db: Session, name: str = "Exit_B") -> Tunnel:
    ru_cloud = Node(name="RU_Cloud", role=NodeRole.ru_cloud, host="ru.example.com", ssh_user="deploy", ssh_port=22)
    exit_node = Node(name=name, role=NodeRole.amnezia_exit, host="exit.example.com", ssh_user="deploy", ssh_port=22)
    db.add_all([ru_cloud, exit_node])
    db.commit()
    tunnel = Tunnel(
        name="awg-exit-b",
        type=TunnelType.amneziawg,
        source_node_id=ru_cloud.id,
        target_node_id=exit_node.id,
        tunnel_cidr="10.240.0.0/30",
        listen_port=9440,
        lan_cidr="0.0.0.0/0",
        enabled=True,
    )
    db.add(tunnel)
    db.commit()
    db.refresh(tunnel)
    return tunnel


def test_routing_policy_defaults_follow_current_behavior() -> None:
    db = _session()
    tunnel = _seed_awg_tunnel(db)

    snapshot = routing_policy_snapshot(db)

    policies = {policy.source: policy for policy in snapshot.policies}
    assert len(snapshot.available_tunnels) == 1
    assert policies[RoutingPolicySource.wg_users_bypass].target == RoutingPolicyTarget.tunnel
    assert policies[RoutingPolicySource.wg_users_bypass].target_tunnel_id == tunnel.id
    assert policies[RoutingPolicySource.wg_users_bypass].resolved_interface == "awg4"
    assert policies[RoutingPolicySource.wg_mikrotik].target_tunnel_id == tunnel.id
    assert policies[RoutingPolicySource.wg_users_default].target == RoutingPolicyTarget.direct
    assert policies[RoutingPolicySource.wg_users_default].direct_interface == "enp3s0"


def test_update_routing_policy_rejects_wireguard_tunnel() -> None:
    db = _session()
    ru_cloud = Node(name="RU_Cloud", role=NodeRole.ru_cloud, host="ru.example.com", ssh_user="deploy", ssh_port=22)
    mikrotik = Node(name="MikroTik", role=NodeRole.mikrotik, host="192.168.50.1", ssh_user="admin", ssh_port=22)
    db.add_all([ru_cloud, mikrotik])
    db.commit()
    tunnel = Tunnel(
        name="wg-mikrotik",
        type=TunnelType.wireguard,
        source_node_id=mikrotik.id,
        target_node_id=ru_cloud.id,
        tunnel_cidr="10.230.0.0/30",
        listen_port=51840,
        lan_cidr="192.168.50.0/24",
        enabled=True,
    )
    db.add(tunnel)
    db.commit()

    try:
        update_routing_policy(
            RoutingPolicySource.wg_mikrotik,
            RoutingPolicyTarget.tunnel,
            tunnel.id,
            None,
            True,
            db,
        )
    except ValueError as exc:
        assert "AmneziaWG" in str(exc)
    else:
        raise AssertionError("Expected WireGuard tunnel to be rejected")


def test_resolved_policy_interface_uses_selected_tunnel() -> None:
    db = _session()
    tunnel = _seed_awg_tunnel(db, "Exit_C")

    update_routing_policy(
        RoutingPolicySource.wg_users_bypass,
        RoutingPolicyTarget.tunnel,
        tunnel.id,
        None,
        True,
        db,
    )

    assert resolved_policy_interface(RoutingPolicySource.wg_users_bypass, db) == "awg3"


def test_routing_policy_preview_contains_expected_sources() -> None:
    db = _session()
    _seed_awg_tunnel(db)

    previews = routing_policy_previews(db)

    by_source = {preview.source: preview for preview in previews}
    assert set(by_source) == {
        RoutingPolicySource.wg_users_bypass,
        RoutingPolicySource.wg_users_default,
        RoutingPolicySource.wg_mikrotik,
    }
    assert by_source[RoutingPolicySource.wg_users_bypass].resolved_interface == "awg4"
    assert any("fwmark 0x77" in command for command in by_source[RoutingPolicySource.wg_users_bypass].commands)
    assert by_source[RoutingPolicySource.wg_users_default].resolved_interface == "enp3s0"
    assert by_source[RoutingPolicySource.wg_mikrotik].resolved_interface == "awg4"
