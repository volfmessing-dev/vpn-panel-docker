from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.node import Node, NodeRole
from app.models.tunnel import TunnelType
from app.services.deployment.tunnel_allocator import create_ru_cloud_uplink


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_create_amnezia_exit_uplink_points_from_ru_cloud_to_exit() -> None:
    db = _session()
    ru_cloud = Node(name="RU_Cloud", role=NodeRole.ru_cloud, host="ru.example.com", ssh_user="deploy", ssh_port=22)
    exit_node = Node(name="Exit_B", role=NodeRole.amnezia_exit, host="exit-b.example.com", ssh_user="deploy", ssh_port=22)
    db.add_all([ru_cloud, exit_node])
    db.commit()

    tunnel = create_ru_cloud_uplink(exit_node, TunnelType.amneziawg, db)

    assert tunnel.type == TunnelType.amneziawg
    assert tunnel.source_node_id == ru_cloud.id
    assert tunnel.target_node_id == exit_node.id
    assert tunnel.tunnel_cidr == "10.240.0.0/30"
    assert tunnel.listen_port == 9440


def test_create_mikrotik_uplink_points_from_mikrotik_to_ru_cloud() -> None:
    db = _session()
    ru_cloud = Node(name="RU_Cloud", role=NodeRole.ru_cloud, host="ru.example.com", ssh_user="deploy", ssh_port=22)
    mikrotik = Node(name="MikroTik", role=NodeRole.mikrotik, host="192.168.50.1", ssh_user="admin", ssh_port=22)
    db.add_all([ru_cloud, mikrotik])
    db.commit()

    tunnel = create_ru_cloud_uplink(mikrotik, TunnelType.wireguard, db)

    assert tunnel.type == TunnelType.wireguard
    assert tunnel.source_node_id == mikrotik.id
    assert tunnel.target_node_id == ru_cloud.id
    assert tunnel.tunnel_cidr == "10.230.0.0/30"
    assert tunnel.listen_port == 51840
    assert tunnel.lan_cidr == "192.168.50.0/24"
