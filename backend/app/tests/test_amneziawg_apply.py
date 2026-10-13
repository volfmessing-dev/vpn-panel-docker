from app.models.node import Node, NodeRole
from app.models.tunnel import Tunnel, TunnelType
from app.services.wireguard import amnezia_apply
from app.services.wireguard.amnezia_apply import (
    awg_tools_bootstrap_script,
    build_exit_awg_config,
    build_ru_cloud_awg_config,
    detect_exit_tunnel_interface,
    ensure_exit_forwarding,
)


def _tunnel() -> Tunnel:
    return Tunnel(
        id=9,
        name="awg-exit-b",
        type=TunnelType.amneziawg,
        source_node_id=1,
        target_node_id=2,
        tunnel_cidr="10.201.0.0/30",
        listen_port=8445,
        lan_cidr="0.0.0.0/0",
        source_private_key="ru-private",
        source_public_key="ru-public",
        target_private_key="exit-private",
        target_public_key="exit-public",
        enabled=True,
    )


def test_build_ru_cloud_awg_config_points_to_exit() -> None:
    exit_node = Node(id=2, name="Exit_B", role=NodeRole.amnezia_exit, host="198.51.100.20", ssh_user="operator", ssh_port=22)

    config = build_ru_cloud_awg_config(_tunnel(), exit_node)

    assert "Address = 10.201.0.1/30" in config
    assert "PrivateKey = ru-private" in config
    assert "PublicKey = exit-public" in config
    assert "Endpoint = 198.51.100.20:8445" in config
    assert "AllowedIPs = 0.0.0.0/0" in config


def test_build_exit_awg_config_uses_detected_egress_interface() -> None:
    ru_cloud = Node(id=1, name="RU_Cloud", role=NodeRole.ru_cloud, host="192.0.2.10", ssh_user="operator", ssh_port=22)

    config = build_exit_awg_config(_tunnel(), ru_cloud, "ens3")

    assert "Address = 10.201.0.2/30" in config
    assert "ListenPort = 8445" in config
    assert "PrivateKey = exit-private" in config
    assert "PublicKey = ru-public" in config
    assert "ip route get 1.1.1.1" in config
    assert '-o "$egress" -j MASQUERADE' in config
    assert "-i %i -o \"$egress\"" in config
    assert "-i \"$egress\" -o %i" in config
    assert "-o ens3 -j MASQUERADE" in config
    assert "AllowedIPs = 10.201.0.1/32" in config


def test_ensure_exit_forwarding_detects_current_interface_and_removes_stale_nat(monkeypatch) -> None:
    exit_node = Node(id=2, name="Exit_B", role=NodeRole.amnezia_exit, host="198.51.100.20", ssh_user="operator", ssh_port=22)
    commands: list[str] = []

    class Completed:
        def __init__(self, stdout: str = "", returncode: int = 0) -> None:
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    def fake_ssh_command(node: Node, command: str, timeout: int):
        commands.append(command)
        if "ip -o -4 addr show" in command:
            return Completed("awg2\n")
        if "ip route get 1.1.1.1" in command and "iptables-save" not in command:
            return Completed("eth0\n")
        return Completed()

    monkeypatch.setattr(amnezia_apply, "ssh_command", fake_ssh_command)

    egress = ensure_exit_forwarding(_tunnel(), exit_node)

    assert egress == "eth0"
    assert any("ip -o -4 addr show" in command and "10.201.0.2" in command for command in commands)
    repair_command = commands[-1]
    assert "iptables-save -t nat" in repair_command
    assert "old_out" in repair_command
    assert '-s "$network" -o "$old_out" -j MASQUERADE' in repair_command
    assert '-s "$network" -o "$egress" -j MASQUERADE' in repair_command
    assert '-i "$interface" -o "$egress"' in repair_command
    assert '-i "$egress" -o "$interface"' in repair_command


def test_detect_exit_tunnel_interface_uses_exit_tunnel_address(monkeypatch) -> None:
    exit_node = Node(id=2, name="Exit_A", role=NodeRole.amnezia_exit, host="203.0.113.30", ssh_user="root", ssh_port=22)
    commands: list[str] = []

    class Completed:
        stdout = "awg2\n"
        stderr = ""
        returncode = 0

    def fake_ssh_command(node: Node, command: str, timeout: int):
        commands.append(command)
        return Completed()

    monkeypatch.setattr(amnezia_apply, "ssh_command", fake_ssh_command)

    interface = detect_exit_tunnel_interface(_tunnel(), exit_node)

    assert interface == "awg2"
    assert len(commands) == 1
    assert "ip -o -4 addr show" in commands[0]
    assert "10.201.0.2" in commands[0]


def test_awg_tools_bootstrap_script_is_idempotent_and_explicit() -> None:
    script = awg_tools_bootstrap_script()

    assert "command -v awg-quick" in script
    assert "command -v awg" in script
    assert "apt-get install" in script
    assert "amneziawg-tools" in script
    assert "Unsupported OS for automatic AmneziaWG install" in script
