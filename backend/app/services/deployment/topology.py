from app.schemas.node import NodeRead
from app.schemas.topology import Topology, TopologyLink


def build_topology(nodes: list[NodeRead]) -> Topology:
    node_names = {node.name for node in nodes}
    links: list[TopologyLink] = []

    if {"MikroTik", "RU_Cloud"}.issubset(node_names):
        links.append(TopologyLink(source="MikroTik", target="RU_Cloud", type="wireguard", status="planned"))

    for exit_name in ["Exit_A", "Exit_B", "Exit_C"]:
        if "RU_Cloud" in node_names and exit_name in node_names:
            links.append(TopologyLink(source="RU_Cloud", target=exit_name, type="amneziawg", status="planned"))

    return Topology(
        nodes=[{"id": node.name, "role": node.role.value, "host": node.host} for node in nodes],
        links=links,
    )
