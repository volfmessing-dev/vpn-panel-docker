import shlex

from app.models.node import Node
from app.models.tunnel import Tunnel, TunnelType
from app.services.deployment.ssh import ssh_command
from app.services.wireguard.exit_policy import exit_interface_name


def stop_removed_tunnel_on_ru_cloud(ru_cloud: Node, tunnel: Tunnel, removed_node: Node) -> str | None:
    if tunnel.type != TunnelType.amneziawg:
        return None

    interface = exit_interface_name(tunnel, removed_node.name)
    command = f"""
set -u
iface={shlex.quote(interface)}
sudo systemctl stop "wg-quick@$iface" >/dev/null 2>&1 || true
sudo systemctl disable "wg-quick@$iface" >/dev/null 2>&1 || true
sudo systemctl stop "$iface-prod.service" >/dev/null 2>&1 || true
sudo systemctl disable "$iface-prod.service" >/dev/null 2>&1 || true
sudo awg-quick down "$iface" >/dev/null 2>&1 || sudo wg-quick down "$iface" >/dev/null 2>&1 || true
sudo ip link del "$iface" >/dev/null 2>&1 || true
sudo rm -f "/etc/wireguard/$iface.conf"
"""
    completed = ssh_command(ru_cloud, f"bash -lc {shlex.quote(command)}", timeout=15)
    if completed.returncode != 0:
        return completed.stderr.strip() or completed.stdout.strip() or f"ssh exited with {completed.returncode}"
    return None
