import base64
import ipaddress
import shlex
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.tunnel import Tunnel
from app.schemas.tunnel import AmneziaWGApplyResult
from app.services.deployment.ssh import ssh_command
from app.services.wireguard.exit_policy import exit_interface_name
from app.services.wireguard.keys import generate_private_key, public_key


def apply_amneziawg_tunnel(tunnel: Tunnel, ru_cloud: Node, exit_node: Node, db: Session) -> AmneziaWGApplyResult:
    ensure_awg_tunnel_keys(tunnel, db)
    if not tunnel.source_public_key or not tunnel.target_public_key:
        raise ValueError("Tunnel keys are incomplete")

    _ensure_awg_tools(exit_node)
    _ensure_awg_tools(ru_cloud)
    interface = exit_interface_name(tunnel, exit_node.name)
    egress_interface = detect_exit_egress_interface(exit_node)
    ru_path = f"/etc/amnezia/{interface}.conf"
    exit_path = f"/etc/amnezia/{interface}-exit.conf"
    ru_config = build_ru_cloud_awg_config(tunnel, exit_node)
    exit_config = build_exit_awg_config(tunnel, ru_cloud, egress_interface)

    exit_result = _install_awg_config(exit_node, exit_path, f"{interface}-exit", exit_config, timeout=30)
    if exit_result.returncode != 0:
        message = exit_result.stderr.strip() or exit_result.stdout.strip() or f"exit ssh exited with {exit_result.returncode}"
        return _result(tunnel, interface, ru_path, exit_path, egress_interface, "failed", message)

    ru_result = _install_awg_config(ru_cloud, ru_path, interface, ru_config, timeout=30)
    if ru_result.returncode != 0:
        message = ru_result.stderr.strip() or ru_result.stdout.strip() or f"ru_cloud ssh exited with {ru_result.returncode}"
        return _result(tunnel, interface, ru_path, exit_path, egress_interface, "failed", message)

    tunnel.applied_at = datetime.now(UTC)
    db.add(tunnel)
    db.commit()
    return _result(tunnel, interface, ru_path, exit_path, egress_interface, "applied", "AmneziaWG tunnel is up")


def ensure_awg_tunnel_keys(tunnel: Tunnel, db: Session) -> Tunnel:
    changed = False
    if not tunnel.source_private_key:
        tunnel.source_private_key = generate_private_key()
        tunnel.source_public_key = public_key(tunnel.source_private_key)
        changed = True
    if not tunnel.target_private_key:
        tunnel.target_private_key = generate_private_key()
        tunnel.target_public_key = public_key(tunnel.target_private_key)
        changed = True
    if changed:
        db.add(tunnel)
        db.commit()
        db.refresh(tunnel)
    return tunnel


def detect_exit_egress_interface(exit_node: Node) -> str:
    command = "ip route get 1.1.1.1 | awk '{for (i=1; i<=NF; i++) if ($i==\"dev\") print $(i+1)}' | head -1"
    completed = ssh_command(exit_node, command, timeout=8)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "Could not detect exit egress interface"
        raise ValueError(message)
    interface = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    if not interface:
        raise ValueError("Could not detect exit egress interface")
    return interface


def detect_exit_tunnel_interface(tunnel: Tunnel, exit_node: Node) -> str:
    network = ipaddress.ip_network(tunnel.tunnel_cidr, strict=False)
    _ru_ip, exit_ip = list(network.hosts())[:2]
    command = (
        f"ip -o -4 addr show | awk -v ip={shlex.quote(str(exit_ip))} "
        "'$4 ~ \"^\" ip \"/\" {print $2; exit}'"
    )
    completed = ssh_command(exit_node, command, timeout=8)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "Could not detect exit tunnel interface"
        raise ValueError(message)
    interface = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    if not interface:
        raise ValueError(f"Could not detect exit tunnel interface for {exit_ip}")
    return interface


def ensure_exit_forwarding(tunnel: Tunnel, exit_node: Node) -> str:
    network = ipaddress.ip_network(tunnel.tunnel_cidr, strict=False)
    interface = detect_exit_tunnel_interface(tunnel, exit_node)
    egress_interface = detect_exit_egress_interface(exit_node)
    command = f"""
set -euo pipefail
network={shlex.quote(str(network))}
interface={shlex.quote(interface)}
egress={shlex.quote(egress_interface)}
sudo sysctl -w net.ipv4.ip_forward=1 >/dev/null
sudo iptables-save -t nat | awk -v net="$network" '
  $1 == "-A" && $2 == "POSTROUTING" {{
    src = ""; out = ""; masquerade = 0
    for (i = 1; i <= NF; i++) {{
      if ($i == "-s") src = $(i + 1)
      if ($i == "-o") out = $(i + 1)
      if ($i == "-j" && $(i + 1) == "MASQUERADE") masquerade = 1
    }}
    if (src == net && masquerade && out != "") print out
  }}
' | while read -r old_out; do
  if [ "$old_out" != "$egress" ]; then
    sudo iptables -t nat -D POSTROUTING -s "$network" -o "$old_out" -j MASQUERADE 2>/dev/null || true
  fi
done
sudo iptables -t nat -C POSTROUTING -s "$network" -o "$egress" -j MASQUERADE 2>/dev/null || sudo iptables -t nat -I POSTROUTING 1 -s "$network" -o "$egress" -j MASQUERADE
sudo iptables -C FORWARD -i "$interface" -o "$egress" -j ACCEPT 2>/dev/null || sudo iptables -I FORWARD 1 -i "$interface" -o "$egress" -j ACCEPT
sudo iptables -C FORWARD -i "$egress" -o "$interface" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || sudo iptables -I FORWARD 2 -i "$egress" -o "$interface" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
"""
    completed = ssh_command(exit_node, f"bash -lc {shlex.quote(command)}", timeout=12)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"Could not ensure exit forwarding on {exit_node.name}"
        raise ValueError(message)
    return egress_interface


def awg_tools_bootstrap_script() -> str:
    return r"""
set -euo pipefail
if command -v awg-quick >/dev/null 2>&1 && command -v awg >/dev/null 2>&1; then
  exit 0
fi

. /etc/os-release
case "${ID:-}" in
  ubuntu|debian)
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl ca-certificates gnupg
    if ! apt-cache show amneziawg-tools >/dev/null 2>&1; then
      curl -fsSL https://ppa.launchpadcontent.net/amnezia/ppa/ubuntu/KEY.gpg | sudo gpg --dearmor -o /usr/share/keyrings/amneziawg.gpg
      echo "deb [signed-by=/usr/share/keyrings/amneziawg.gpg] https://ppa.launchpadcontent.net/amnezia/ppa/ubuntu jammy main" | sudo tee /etc/apt/sources.list.d/amneziawg.list >/dev/null
      sudo apt-get update
    fi
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends amneziawg amneziawg-tools
    ;;
  *)
    echo "Unsupported OS for automatic AmneziaWG install: ${ID:-unknown}" >&2
    exit 42
    ;;
esac

command -v awg-quick >/dev/null 2>&1
command -v awg >/dev/null 2>&1
"""


def _ensure_awg_tools(node: Node) -> None:
    completed = ssh_command(node, f"bash -lc {shlex.quote(awg_tools_bootstrap_script())}", timeout=120)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"Could not bootstrap AmneziaWG tools on {node.name}"
        raise ValueError(message)


def build_ru_cloud_awg_config(tunnel: Tunnel, exit_node: Node) -> str:
    network = ipaddress.ip_network(tunnel.tunnel_cidr, strict=False)
    ru_ip, _exit_ip = list(network.hosts())[:2]
    return f"""[Interface]
Address = {ru_ip}/{network.prefixlen}
PrivateKey = {tunnel.source_private_key}
Jc = 4
Jmin = 40
Jmax = 70
S1 = 0
S2 = 0
H1 = 1
H2 = 2
H3 = 3
H4 = 4
PostUp = sysctl -w net.ipv4.ip_forward=1 >/dev/null
PostDown = true

[Peer]
PublicKey = {tunnel.target_public_key}
Endpoint = {exit_node.host}:{tunnel.listen_port}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""


def build_exit_awg_config(tunnel: Tunnel, ru_cloud: Node, egress_interface: str) -> str:
    network = ipaddress.ip_network(tunnel.tunnel_cidr, strict=False)
    ru_ip, exit_ip = list(network.hosts())[:2]
    post_up = (
        "egress=$(ip route get 1.1.1.1 | awk '{for (i=1; i<=NF; i++) if ($i==\"dev\") print $(i+1)}' | head -1); "
        f"test -n \"$egress\"; sysctl -w net.ipv4.ip_forward=1 >/dev/null; "
        f"iptables -t nat -C POSTROUTING -s {network} -o \"$egress\" -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s {network} -o \"$egress\" -j MASQUERADE; "
        f"iptables -C FORWARD -i %i -o \"$egress\" -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -i %i -o \"$egress\" -j ACCEPT; "
        f"iptables -C FORWARD -i \"$egress\" -o %i -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || iptables -I FORWARD 2 -i \"$egress\" -o %i -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT"
    )
    return f"""[Interface]
Address = {exit_ip}/{network.prefixlen}
ListenPort = {tunnel.listen_port}
PrivateKey = {tunnel.target_private_key}
Jc = 4
Jmin = 40
Jmax = 70
S1 = 0
S2 = 0
H1 = 1
H2 = 2
H3 = 3
H4 = 4
PostUp = {post_up}
PostDown = iptables -t nat -D POSTROUTING -s {network} -o {egress_interface} -j MASQUERADE 2>/dev/null || true

[Peer]
PublicKey = {tunnel.source_public_key}
AllowedIPs = {ru_ip}/32
"""


def _install_awg_config(node: Node, config_path: str, service_name: str, config: str, timeout: int):
    encoded = base64.b64encode(config.encode()).decode()
    command = f"""
set -euo pipefail
path={shlex.quote(config_path)}
service={shlex.quote(service_name)}
sudo mkdir -p "$(dirname "$path")" /var/backups/vpn-panel
if [ -f "$path" ]; then
  sudo cp "$path" "/var/backups/vpn-panel/$(basename "$path").$(date +%Y%m%d%H%M%S).bak"
fi
printf %s {shlex.quote(encoded)} | base64 -d | sudo tee "$path" >/dev/null
sudo chmod 600 "$path"
sudo sysctl -w net.ipv4.ip_forward=1 >/dev/null
sudo systemctl stop "awg-quick@$service" >/dev/null 2>&1 || sudo systemctl stop "wg-quick@$service" >/dev/null 2>&1 || true
sudo awg-quick down "$path" >/dev/null 2>&1 || sudo wg-quick down "$path" >/dev/null 2>&1 || true
if command -v awg-quick >/dev/null 2>&1; then
  sudo awg-quick up "$path"
else
  sudo wg-quick up "$path"
fi
if command -v awg >/dev/null 2>&1; then
  sudo awg show "$service" >/dev/null
else
  sudo wg show "$service" >/dev/null
fi
"""
    return ssh_command(node, f"bash -lc {shlex.quote(command)}", timeout=timeout)


def _result(
    tunnel: Tunnel,
    interface: str,
    ru_path: str,
    exit_path: str,
    egress_interface: str,
    status: str,
    message: str,
) -> AmneziaWGApplyResult:
    return AmneziaWGApplyResult(
        tunnel_id=tunnel.id,
        name=tunnel.name,
        status=status,
        message=message,
        interface_name=interface,
        ru_cloud_config_path=ru_path,
        exit_config_path=exit_path,
        exit_egress_interface=egress_interface,
        source_public_key=tunnel.source_public_key or "",
        target_public_key=tunnel.target_public_key or "",
    )
