from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.node import Node, NodeRole
from app.models.routing_policy import RoutingPolicySource, RoutingPolicyTarget
from app.models.tunnel import Tunnel, TunnelType
from app.services.wireguard.apply import build_ru_cloud_config
from app.services.wireguard.routing_policy import resolved_policy_interface, update_routing_policy
from app.services.wireguard.users import _policy_script


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_tunnel(db: Session, exit_name: str) -> Tunnel:
    ru_cloud = Node(name="RU_Cloud", role=NodeRole.ru_cloud, host="ru.example.com", ssh_user="deploy", ssh_port=22)
    exit_node = Node(name=exit_name, role=NodeRole.amnezia_exit, host="exit.example.com", ssh_user="deploy", ssh_port=22)
    db.add_all([ru_cloud, exit_node])
    db.commit()
    tunnel = Tunnel(
        name=f"awg-{exit_name.lower()}",
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


def test_user_policy_script_does_not_replace_main_default_for_direct_default() -> None:
    script = _policy_script([], "awg4", "enp3s0", default_uses_tunnel=False)

    assert "ip route replace default dev awg4 table vpn_panel_exit" in script
    assert "ip route replace default dev enp3s0" not in script
    assert "ip rule add from 10.90.0.0/24 table vpn_panel_exit priority 12091" not in script


def test_user_policy_script_adds_source_rule_for_tunneled_default() -> None:
    script = _policy_script([], "awg4", "awg4", default_uses_tunnel=True)

    assert "ip rule add from 10.90.0.0/24 table vpn_panel_exit priority 12091" in script


def test_user_policy_script_has_no_bundled_bypass_ranges() -> None:
    from app.services.wireguard.users import BYPASS_CIDRS, BYPASS_DOMAINS
    assert BYPASS_CIDRS == []
    assert BYPASS_DOMAINS == []
    script = _policy_script([], "awg4", "enp3s0", default_uses_tunnel=False)
    assert "ipset swap vpn_panel_bypass_v4_next vpn_panel_bypass_v4" in script
    assert "ipset flush vpn_panel_bypass_v4" not in script
    assert len(script) < 5000


def test_mikrotik_config_can_use_selected_policy_interface() -> None:
    db = _session()
    tunnel = _seed_tunnel(db, "Exit_C")
    update_routing_policy(
        RoutingPolicySource.wg_mikrotik,
        RoutingPolicyTarget.tunnel,
        tunnel.id,
        None,
        True,
        db,
    )
    mikrotik_tunnel = Tunnel(
        name="wg-mikrotik",
        type=TunnelType.wireguard,
        source_node_id=1,
        target_node_id=2,
        tunnel_cidr="10.230.0.0/30",
        listen_port=51840,
        lan_cidr="192.168.50.0/24",
        source_public_key="source-public",
        target_private_key="target-private",
    )

    config = build_ru_cloud_config(mikrotik_tunnel, resolved_policy_interface(RoutingPolicySource.wg_mikrotik, db))

    assert "ip route replace default dev awg3 table vpn_panel_exit" in config
    assert "-o awg3 -j MASQUERADE" in config


def test_bypass_mark_is_saved_before_awg_udp_restore() -> None:
    script = _policy_script([], "awg1", "enp3s0")
    save = "-m mark --mark 0x77 -j CONNMARK --save-mark"
    assert save in script
    assert script.index("-j MARK --set-mark 0x77") < script.index(save)
