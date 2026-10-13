import base64
import ipaddress
import shlex
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.tunnel import Tunnel
from app.schemas.tunnel import TunnelApplyResult
from app.services.deployment.ssh import ssh_command
from app.models.routing_policy import RoutingPolicySource
from app.services.wireguard.exit_policy import EXIT_TABLE, available_exit_interface
from app.services.wireguard.keys import generate_private_key, public_key
from app.services.wireguard.routing_policy import resolved_policy_interface_or_default


def ensure_tunnel_keys(tunnel: Tunnel, db: Session) -> Tunnel:
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


def apply_ru_cloud_tunnel(tunnel: Tunnel, source: Node, target: Node, db: Session) -> TunnelApplyResult:
    ensure_tunnel_keys(tunnel, db)
    if not tunnel.source_public_key or not tunnel.target_public_key or not tunnel.target_private_key:
        raise ValueError("Tunnel keys are incomplete")

    config_path = "/etc/wireguard/wg-ru-cloud.conf"
    exit_interface = resolved_policy_interface_or_default(
        RoutingPolicySource.wg_mikrotik,
        db,
        available_exit_interface(db),
    )
    config = build_ru_cloud_config(tunnel, exit_interface)
    encoded_config = base64.b64encode(config.encode()).decode()
    remote_command = f"""
set -eu
sudo mkdir -p /etc/wireguard
printf %s {shlex.quote(encoded_config)} | base64 -d | sudo tee {shlex.quote(config_path)} >/dev/null
sudo chmod 600 {shlex.quote(config_path)}
sudo sysctl -w net.ipv4.ip_forward=1 >/dev/null
if systemctl list-unit-files wg-quick@.service >/dev/null 2>&1; then
  sudo systemctl stop wg-quick@wg-ru-cloud >/dev/null 2>&1 || true
  sudo systemctl enable --now wg-quick@wg-ru-cloud
else
  sudo wg-quick down wg-ru-cloud >/dev/null 2>&1 || true
  sudo wg-quick up wg-ru-cloud
fi
sudo wg show wg-ru-cloud >/dev/null
"""
    completed = ssh_command(target, remote_command, timeout=20)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"ssh exited with {completed.returncode}"
        return TunnelApplyResult(
            tunnel_id=tunnel.id,
            name=tunnel.name,
            status="failed",
            message=message,
            ru_cloud_config_path=config_path,
            source_public_key=tunnel.source_public_key,
            target_public_key=tunnel.target_public_key,
        )

    tunnel.applied_at = datetime.now(UTC)
    db.add(tunnel)
    db.commit()
    return TunnelApplyResult(
        tunnel_id=tunnel.id,
        name=tunnel.name,
        status="applied",
        message="RU_Cloud WireGuard interface is up",
        ru_cloud_config_path=config_path,
        source_public_key=tunnel.source_public_key,
        target_public_key=tunnel.target_public_key,
    )


def build_ru_cloud_config(tunnel: Tunnel, exit_interface: str = "awg4") -> str:
    network = ipaddress.ip_network(tunnel.tunnel_cidr, strict=False)
    hosts = list(network.hosts())
    target_ip = hosts[0]
    source_ip = hosts[1]
    return f"""[Interface]
Address = {target_ip}/{network.prefixlen}
ListenPort = {tunnel.listen_port}
PrivateKey = {tunnel.target_private_key}
PostUp = ip rule add from {tunnel.lan_cidr} table {EXIT_TABLE} priority 12031 2>/dev/null || true
PostUp = ip rule add from {source_ip}/32 table {EXIT_TABLE} priority 12032 2>/dev/null || true
PostUp = ip route replace default dev {exit_interface} table {EXIT_TABLE}
PostUp = iptables -t nat -C POSTROUTING -s {tunnel.lan_cidr} -o {exit_interface} -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s {tunnel.lan_cidr} -o {exit_interface} -j MASQUERADE
PostUp = iptables -t nat -C POSTROUTING -s {source_ip}/32 -o {exit_interface} -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s {source_ip}/32 -o {exit_interface} -j MASQUERADE
PostDown = ip rule del from {tunnel.lan_cidr} table {EXIT_TABLE} priority 12031 2>/dev/null || true
PostDown = ip rule del from {source_ip}/32 table {EXIT_TABLE} priority 12032 2>/dev/null || true
PostDown = iptables -t nat -D POSTROUTING -s {tunnel.lan_cidr} -o {exit_interface} -j MASQUERADE 2>/dev/null || true
PostDown = iptables -t nat -D POSTROUTING -s {source_ip}/32 -o {exit_interface} -j MASQUERADE 2>/dev/null || true

[Peer]
PublicKey = {tunnel.source_public_key}
AllowedIPs = {source_ip}/32, {tunnel.lan_cidr}
"""
