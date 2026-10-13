import base64
import ipaddress
import re
import shlex
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.node import Node
from app.models.routing_policy import RoutingPolicySource
from app.models.vpn_user import VpnUser
from app.schemas.vpn_user import VpnUserApplyResult, VpnUserConfig, VpnUserRead
from app.services.deployment.ssh import ssh_command
from app.services.wireguard.exit_policy import DIRECT_INTERFACE, EXIT_TABLE, available_exit_interface
from app.services.wireguard.keys import generate_private_key, public_key
from app.services.wireguard.routing_policy import policy_uses_tunnel, resolved_policy_interface_or_default

CLIENT_NETWORK = ipaddress.ip_network("10.90.0.0/24")
CLIENT_DNS = "1.1.1.1"
RU_INTERFACE = "wg-ru-cloud"
USER_BYPASS_SET = "vpn_panel_bypass_v4"
USER_BYPASS_MARK = "0x77"
MANAGED_BEGIN = "# BEGIN VPN-PANEL USERS"
MANAGED_END = "# END VPN-PANEL USERS"
BYPASS_DOMAINS: list[str] = []
BYPASS_CIDRS = [str(ipaddress.IPv4Network(c.strip())) for c in get_settings().bypass_cidrs.split(",") if c.strip()]
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def create_vpn_user(payload_name: str, enabled: bool, db: Session) -> VpnUser:
    private_key = generate_private_key()
    user = VpnUser(
        name=payload_name,
        client_ip=_next_client_ip(db),
        private_key=private_key,
        public_key=public_key(private_key),
        enabled=enabled,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_vpn_users_with_handshakes(ru_cloud: Node, db: Session) -> list[VpnUserRead]:
    users = list(db.scalars(select(VpnUser).order_by(VpnUser.id)).all())
    handshakes = collect_user_handshakes(ru_cloud)
    result = []
    for user in users:
        latest_handshake = handshakes.get(user.public_key)
        result.append(
            VpnUserRead(
                id=user.id,
                name=user.name,
                client_ip=user.client_ip,
                public_key=user.public_key,
                enabled=user.enabled,
                applied_at=user.applied_at,
                latest_handshake=latest_handshake,
                latest_handshake_at=datetime.fromtimestamp(latest_handshake, UTC) if latest_handshake else None,
            )
        )
    return result


def collect_user_handshakes(ru_cloud: Node) -> dict[str, int]:
    command = f"sudo wg show {shlex.quote(RU_INTERFACE)} dump 2>/dev/null || true"
    completed = ssh_command(ru_cloud, command, timeout=8)
    if completed.returncode != 0:
        return {}

    handshakes: dict[str, int] = {}
    for line in completed.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) < 6:
            continue
        public_key = fields[1]
        if public_key in {"", "(none)"}:
            continue
        try:
            latest_handshake = int(fields[5])
        except ValueError:
            continue
        if latest_handshake > 0:
            handshakes[public_key] = latest_handshake
    return handshakes


def build_user_config(user: VpnUser, ru_cloud: Node) -> VpnUserConfig:
    config = f"""[Interface]
PrivateKey = {user.private_key}
Address = {user.client_ip}/32
DNS = {CLIENT_DNS}

[Peer]
PublicKey = {_ru_cloud_public_key(ru_cloud)}
Endpoint = {ru_cloud.host}:8443
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""
    return VpnUserConfig(
        user_id=user.id,
        name=user.name,
        filename=f"{user.name}.conf",
        config=config,
    )


def bypass_domains() -> list[str]:
    path = Path(get_settings().bypass_domains_path)
    if not path.exists():
        return BYPASS_DOMAINS.copy()
    domains = [line.strip().lower() for line in path.read_text().splitlines()]
    domains = [line for line in domains if line and not line.startswith("#")]
    return _normalize_bypass_domains(domains) or BYPASS_DOMAINS.copy()


def update_bypass_domains(domains: list[str]) -> list[str]:
    normalized = _normalize_bypass_domains(domains)
    path = Path(get_settings().bypass_domains_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(normalized) + "\n")
    return normalized


def collect_bypass_status(ru_cloud: Node) -> dict[str, object]:
    domains = bypass_domains()
    command = f"""
set -eu
echo 'domains:'
printf '%s\\n' {' '.join(shlex.quote(domain) for domain in domains)}
echo 'ips:'
sudo ipset list {USER_BYPASS_SET} 2>/dev/null | awk '/^[0-9]+\\./ {{print}}' | sort -V || true
echo 'rules:'
ip rule show | grep -E 'fwmark|{EXIT_TABLE}' || true
echo 'mangle:'
sudo iptables -t mangle -S PREROUTING | grep {USER_BYPASS_SET} || true
"""
    completed = ssh_command(ru_cloud, command, timeout=12)
    if completed.returncode != 0:
        return {
            "status": "down",
            "domains": domains,
            "ips": [],
            "rules": [],
            "mangle": [],
            "error": completed.stderr.strip() or completed.stdout.strip(),
        }
    sections: dict[str, list[str]] = {"domains": [], "ips": [], "rules": [], "mangle": []}
    current: str | None = None
    for line in completed.stdout.splitlines():
        if line.endswith(":") and line[:-1] in sections:
            current = line[:-1]
            continue
        if current and line.strip():
            sections[current].append(line.strip())
    return {
        "status": "up",
        "domains": sections["domains"] or domains,
        "ips": sections["ips"],
        "rules": sections["rules"],
        "mangle": sections["mangle"],
        "error": None,
    }


def apply_vpn_users(ru_cloud: Node, db: Session) -> VpnUserApplyResult:
    users = list(db.scalars(select(VpnUser).order_by(VpnUser.id)).all())
    enabled_users = [user for user in users if user.enabled]
    fallback_exit_interface = available_exit_interface(db)
    bypass_interface = resolved_policy_interface_or_default(
        RoutingPolicySource.wg_users_bypass,
        db,
        fallback_exit_interface,
    )
    default_interface = resolved_policy_interface_or_default(
        RoutingPolicySource.wg_users_default,
        db,
        DIRECT_INTERFACE,
    )
    default_uses_tunnel = policy_uses_tunnel(RoutingPolicySource.wg_users_default, db)
    managed_block = _managed_peer_block(enabled_users)
    encoded_block = base64.b64encode(managed_block.encode()).decode()
    policy_script = _policy_script(enabled_users, bypass_interface, default_interface, default_uses_tunnel)
    encoded_script = base64.b64encode(policy_script.encode()).decode()
    runtime_commands = "\n".join(
        f"sudo wg set {RU_INTERFACE} peer {shlex.quote(user.public_key)} allowed-ips {shlex.quote(user.client_ip + '/32')}"
        for user in enabled_users
    )
    remote_command = f"""
set -eu
sudo test -f /etc/wireguard/{RU_INTERFACE}.conf
tmp="$(mktemp)"
sudo awk '/^{MANAGED_BEGIN}$/ {{skip=1; next}} /^{MANAGED_END}$/ {{skip=0; next}} skip==0 {{print}}' /etc/wireguard/{RU_INTERFACE}.conf > "$tmp"
printf '\\n%s\\n' {shlex.quote(encoded_block)} | base64 -d >> "$tmp"
sudo install -m 600 "$tmp" /etc/wireguard/{RU_INTERFACE}.conf
rm -f "$tmp"
printf %s {shlex.quote(encoded_script)} | base64 -d | sudo tee /usr/local/sbin/vpn-panel-users-up.sh >/dev/null
sudo chmod 700 /usr/local/sbin/vpn-panel-users-up.sh
sudo tee /etc/systemd/system/vpn-panel-users.service >/dev/null <<'UNIT'
[Unit]
Description=VPN panel user split bypass routing
After=wg-quick@{RU_INTERFACE}.service
Wants=wg-quick@{RU_INTERFACE}.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/vpn-panel-users-up.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
sudo tee /etc/systemd/system/vpn-panel-refresh-users.service >/dev/null <<'UNIT'
[Unit]
Description=Atomically refresh VPN panel bypass IP set
After=network-online.target vpn-panel-users.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/vpn-panel-users-up.sh --refresh-only
TimeoutStartSec=180
UNIT
sudo tee /etc/systemd/system/vpn-panel-refresh-users.timer >/dev/null <<'UNIT'
[Unit]
Description=Refresh VPN panel user bypass IP set

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Unit=vpn-panel-refresh-users.service

[Install]
WantedBy=timers.target
UNIT
sudo systemctl disable --now vpn-panel-users.timer >/dev/null 2>&1 || true
sudo systemctl daemon-reload
sudo systemctl enable vpn-panel-users.service >/dev/null
sudo systemctl enable --now vpn-panel-refresh-users.timer >/dev/null
sudo systemctl restart vpn-panel-refresh-users.timer
sudo sysctl -w net.ipv4.ip_forward=1 >/dev/null
sudo ip route replace default dev {bypass_interface} table {EXIT_TABLE}
sudo iptables -t nat -C POSTROUTING -s {CLIENT_NETWORK} -o {bypass_interface} -j MASQUERADE 2>/dev/null || sudo iptables -t nat -A POSTROUTING -s {CLIENT_NETWORK} -o {bypass_interface} -j MASQUERADE
sudo iptables -t nat -C POSTROUTING -s {CLIENT_NETWORK} -o {default_interface} -j MASQUERADE 2>/dev/null || sudo iptables -t nat -A POSTROUTING -s {CLIENT_NETWORK} -o {default_interface} -j MASQUERADE
if sudo wg show {RU_INTERFACE} >/dev/null 2>&1; then
  sync_tmp="$(mktemp)"
  sudo wg-quick strip {RU_INTERFACE} > "$sync_tmp"
  sudo wg syncconf {RU_INTERFACE} "$sync_tmp"
  rm -f "$sync_tmp"
else
  sudo systemctl restart wg-quick@{RU_INTERFACE}
fi
{runtime_commands}
sudo /usr/local/sbin/vpn-panel-users-up.sh
sudo wg show {RU_INTERFACE} >/dev/null
"""
    completed = ssh_command(ru_cloud, f"bash -lc {shlex.quote(remote_command)}", timeout=180)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"ssh exited with {completed.returncode}"
        return VpnUserApplyResult(status="failed", message=message, applied_users=0)

    applied_at = datetime.now(UTC)
    for user in enabled_users:
        user.applied_at = applied_at
        db.add(user)
    db.commit()
    return VpnUserApplyResult(
        status="applied",
        message=f"Applied {len(enabled_users)} user peers to {RU_INTERFACE}; bypass domains use {bypass_interface}, other traffic uses {default_interface}",
        applied_users=len(enabled_users),
    )


def _next_client_ip(db: Session) -> str:
    used = set(db.scalars(select(VpnUser.client_ip)).all())
    hosts = list(CLIENT_NETWORK.hosts())
    for host in hosts[10:]:
        ip = str(host)
        if ip not in used:
            return ip
    raise ValueError(f"No free addresses in {CLIENT_NETWORK}")


def _managed_peer_block(users: list[VpnUser]) -> str:
    blocks = [MANAGED_BEGIN]
    for user in users:
        blocks.append(
            f"""

[Peer]
# vpn-panel user: {user.name}
PublicKey = {user.public_key}
AllowedIPs = {user.client_ip}/32
"""
        )
    blocks.append(MANAGED_END)
    return "\n".join(blocks)


def _policy_script(
    users: list[VpnUser],
    bypass_interface: str,
    default_interface: str,
    default_uses_tunnel: bool = False,
) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "exec 9>/run/lock/vpn-panel-bypass.lock",
        "flock -w 30 9",
    ]
    lines.extend(_bypass_refresh_lines())
    lines.extend([
        'if [[ "${1:-}" == "--refresh-only" ]]; then exit 0; fi',
        "sysctl -w net.ipv4.ip_forward=1 >/dev/null",
        f"ip route replace {CLIENT_NETWORK} dev {RU_INTERFACE}",
        f"ip route replace default dev {bypass_interface} table {EXIT_TABLE}",
        f"ip rule show | grep -q '^12089:.*to {CLIENT_NETWORK} lookup main$' || ip rule add to {CLIENT_NETWORK} lookup main priority 12089",
        f"ip rule show | grep -q '^12090:.*fwmark {USER_BYPASS_MARK} lookup {EXIT_TABLE}$' || ip rule add fwmark {USER_BYPASS_MARK} table {EXIT_TABLE} priority 12090",
        f"ip rule del from {CLIENT_NETWORK} table {EXIT_TABLE} priority 12091 2>/dev/null || true",
    ])
    if default_uses_tunnel:
        lines.append(f"ip rule add from {CLIENT_NETWORK} table {EXIT_TABLE} priority 12091")
    lines.extend([
        f"iptables -t mangle -C PREROUTING -i {RU_INTERFACE} -s {CLIENT_NETWORK} -m set --match-set {USER_BYPASS_SET} dst -j MARK --set-mark {USER_BYPASS_MARK} 2>/dev/null || iptables -t mangle -I PREROUTING 1 -i {RU_INTERFACE} -s {CLIENT_NETWORK} -m set --match-set {USER_BYPASS_SET} dst -j MARK --set-mark {USER_BYPASS_MARK}",
        f"iptables -t mangle -C PREROUTING -i {RU_INTERFACE} -s {CLIENT_NETWORK} -m mark --mark {USER_BYPASS_MARK} -j CONNMARK --save-mark 2>/dev/null || iptables -t mangle -A PREROUTING -i {RU_INTERFACE} -s {CLIENT_NETWORK} -m mark --mark {USER_BYPASS_MARK} -j CONNMARK --save-mark",
        f"iptables -t nat -C POSTROUTING -s {CLIENT_NETWORK} -o {default_interface} -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s {CLIENT_NETWORK} -o {default_interface} -j MASQUERADE",
        f"iptables -t nat -C POSTROUTING -s {CLIENT_NETWORK} -o {bypass_interface} -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s {CLIENT_NETWORK} -o {bypass_interface} -j MASQUERADE",
        "for priority in $(seq 12100 12399); do ip rule del priority \"$priority\" 2>/dev/null || true; done",
    ])
    for user in users:
        lines.append(f"ip rule del from {user.client_ip}/32 table {EXIT_TABLE} priority {12100 + user.id} 2>/dev/null || true")
    return "\n".join(lines) + "\n"


def _bypass_refresh_lines() -> list[str]:
    """Build offline, then replace the referenced set with one atomic swap."""
    staging = f"{USER_BYPASS_SET}_next"
    lines = [
        f"if ! ipset list {USER_BYPASS_SET} -terse >/dev/null 2>&1; then",
        "  if test -s /var/lib/vpn-panel-bypass.ipset; then",
        "    ipset restore -exist < /var/lib/vpn-panel-bypass.ipset",
        "  else",
        f"    ipset create {USER_BYPASS_SET} hash:ip family inet timeout 86400",
        "  fi",
        "fi",
        'work="$(mktemp -d /run/vpn-panel-bypass.XXXXXX)"',
        f"trap 'ipset destroy {staging} 2>/dev/null || true; rm -rf \"$work\"' EXIT",
        f"ipset destroy {staging} 2>/dev/null || true",
        f"ipset create {staging} hash:ip family inet timeout 86400",
        ': > "$work/ips"',
        "resolve_domain() {",
        '  local answer',
        '  answer="$(dig +time=2 +tries=1 +noall +comments +answer A "$1")" || return 1',
        "  printf '%s\\n' \"$answer\" | grep -Eq 'status: (NOERROR|NXDOMAIN),' || return 1",
        "  printf '%s\\n' \"$answer\" | awk '$4 == \"A\" {print $5}' >> \"$work/ips\"",
        "}",
    ]
    for domain in bypass_domains():
        lines.append(f"resolve_domain {shlex.quote(domain)}")
    cidr_expander = (
        "import ipaddress; "
        f"cidrs={BYPASS_CIDRS!r}; "
        "[print(ip) for cidr in cidrs for ip in ipaddress.ip_network(cidr)]"
    )
    lines.extend([
        f'python3 -c {shlex.quote(cidr_expander)} >> "$work/ips"',
        'sort -u "$work/ips" > "$work/unique"',
        'test -s "$work/unique"',
        f"awk '{{print \"add {staging} \" $0 \" timeout 86400\"}}' \"$work/unique\" > \"$work/restore\"",
        'ipset restore < "$work/restore"',
        f"ipset create {USER_BYPASS_SET} hash:ip family inet timeout 86400 -exist",
        f"ipset swap {staging} {USER_BYPASS_SET}",
        'saved="$(mktemp /var/lib/vpn-panel-bypass.ipset.XXXXXX)"',
        f'ipset save {USER_BYPASS_SET} > "$saved"',
        'chmod 600 "$saved"',
        'mv -f "$saved" /var/lib/vpn-panel-bypass.ipset',
        'printf "bypass refresh complete: %s entries\\n" "$(wc -l < "$work/unique")"',
    ])
    return lines


def _normalize_bypass_domains(domains: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for raw_domain in domains:
        domain = raw_domain.strip().lower().rstrip(".")
        if not domain:
            continue
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError(f"Invalid domain: {raw_domain}")
        if domain not in seen:
            normalized.append(domain)
            seen.add(domain)
    return normalized


def _ru_cloud_public_key(ru_cloud: Node) -> str:
    command = f"sudo wg show {RU_INTERFACE} public-key"
    completed = ssh_command(ru_cloud, command, timeout=8)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "Could not read RU_Cloud WireGuard public key"
        raise ValueError(message)
    return completed.stdout.strip()
