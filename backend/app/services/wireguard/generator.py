from app.schemas.node import NodeRead


def build_config_preview(nodes: list[NodeRead]) -> str:
    names = {node.name for node in nodes}
    lines = [
        "# Generated preview. Dry-run only.",
        "# MikroTik marks bypass traffic and sends it to RU_Cloud over WireGuard.",
        "",
    ]

    if {"MikroTik", "RU_Cloud"}.issubset(names):
        lines.extend(
            [
                "[wireguard mikrotik-ru]",
                "local = MikroTik",
                "remote = RU_Cloud",
                "network = 10.200.0.0/30",
                "",
            ]
        )

    for exit_name in ["Exit_A", "Exit_B", "Exit_C"]:
        if exit_name in names and "RU_Cloud" in names:
            lines.extend(
                [
                    f"[amneziawg ru-{exit_name.lower().split('_')[0]}]",
                    "local = RU_Cloud",
                    f"remote = {exit_name}",
                    "allowed_ips = 192.168.50.0/24",
                    "",
                ]
            )

    return "\n".join(lines)
