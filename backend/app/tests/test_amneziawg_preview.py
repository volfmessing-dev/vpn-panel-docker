from app.models.node import Node, NodeRole
from app.models.tunnel import Tunnel, TunnelType
from app.services.wireguard.tunnel_preview import build_amneziawg_preview


def test_amneziawg_preview_builds_ru_cloud_and_exit_configs() -> None:
    ru_cloud = Node(id=1, name="RU_Cloud", role=NodeRole.ru_cloud, host="192.0.2.10", ssh_user="operator", ssh_port=22)
    exit_node = Node(id=2, name="Exit_B", role=NodeRole.amnezia_exit, host="198.51.100.20", ssh_user="operator", ssh_port=22)
    tunnel = Tunnel(
        id=7,
        name="awg-exit-b",
        type=TunnelType.amneziawg,
        source_node_id=ru_cloud.id,
        target_node_id=exit_node.id,
        tunnel_cidr="10.201.0.0/30",
        listen_port=8445,
        lan_cidr="0.0.0.0/0",
        source_private_key="ru-private",
        source_public_key="ru-public",
        target_private_key="exit-private",
        target_public_key="exit-public",
        enabled=True,
    )

    preview = build_amneziawg_preview(tunnel, ru_cloud, exit_node)

    assert preview.type == TunnelType.amneziawg
    assert preview.interface_name == "awg4"
    assert preview.source_tunnel_ip == "10.201.0.1"
    assert preview.target_tunnel_ip == "10.201.0.2"
    assert preview.endpoint == "198.51.100.20:8445"
    assert preview.ru_cloud_config_path == "/etc/amnezia/awg4.conf"
    assert preview.exit_config_path == "/etc/amnezia/awg4-exit.conf"
    assert "Address = 10.201.0.1/30" in preview.ru_cloud_config
    assert "Endpoint = 198.51.100.20:8445" in preview.ru_cloud_config
    assert "PublicKey = exit-public" in preview.ru_cloud_config
    assert preview.exit_config is not None
    assert "Address = 10.201.0.2/30" in preview.exit_config
    assert "ListenPort = 8445" in preview.exit_config
    assert "PublicKey = ru-public" in preview.exit_config


def test_amneziawg_preview_rejects_too_small_network() -> None:
    ru_cloud = Node(id=1, name="RU_Cloud", role=NodeRole.ru_cloud, host="ru.example.com", ssh_user="deploy", ssh_port=22)
    exit_node = Node(id=2, name="Exit", role=NodeRole.amnezia_exit, host="exit.example.com", ssh_user="deploy", ssh_port=22)
    tunnel = Tunnel(
        id=8,
        name="awg-exit",
        type=TunnelType.amneziawg,
        source_node_id=ru_cloud.id,
        target_node_id=exit_node.id,
        tunnel_cidr="10.201.0.0/32",
        listen_port=9440,
        lan_cidr="0.0.0.0/0",
        enabled=True,
    )

    try:
        build_amneziawg_preview(tunnel, ru_cloud, exit_node)
    except ValueError as exc:
        assert "at least two host addresses" in str(exc)
    else:
        raise AssertionError("Expected invalid AWG tunnel network to fail")
