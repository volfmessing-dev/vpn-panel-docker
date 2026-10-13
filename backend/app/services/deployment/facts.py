import subprocess

from app.models.node import Node, NodeRole
from app.schemas.facts import NodeFacts
from app.services.deployment.ssh import ssh_command


FACTS_SCRIPT = r"""
set -eu
printf 'HOSTNAME=%s\n' "$(hostname 2>/dev/null || true)"
printf 'KERNEL=%s\n' "$(uname -sr 2>/dev/null || true)"
if [ -r /etc/os-release ]; then
  . /etc/os-release
  printf 'OS=%s\n' "${PRETTY_NAME:-unknown}"
else
  printf 'OS=%s\n' "unknown"
fi
printf 'PUBLIC_IP=%s\n' "$(curl -fsS --max-time 3 https://api.ipify.org 2>/dev/null || curl -fsS --max-time 3 https://ifconfig.me 2>/dev/null || true)"
printf 'IP_FORWARD=%s\n' "$(sysctl -n net.ipv4.ip_forward 2>/dev/null || cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || true)"
printf 'DOCKER=%s\n' "$(docker --version 2>/dev/null || true)"
printf 'WIREGUARD=%s\n' "$(wg --version 2>/dev/null || awg --version 2>/dev/null || true)"
printf 'INTERFACES_BEGIN\n'
ip -brief address 2>/dev/null | head -30 || true
printf 'INTERFACES_END\n'
printf 'ROUTES_BEGIN\n'
ip route 2>/dev/null | head -40 || true
printf 'ROUTES_END\n'
"""


def collect_node_facts(node: Node) -> NodeFacts:
    if node.role == NodeRole.mikrotik:
        return NodeFacts(
            node_id=node.id,
            name=node.name,
            status="unsupported",
            error="MikroTik facts collection will use RouterOS API in a later step",
        )

    try:
        completed = ssh_command(node, FACTS_SCRIPT, timeout=14)
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired) as exc:
        return NodeFacts(node_id=node.id, name=node.name, status="down", error=str(exc))

    if completed.returncode != 0:
        error = completed.stderr.strip() or completed.stdout.strip() or f"ssh exited with {completed.returncode}"
        return NodeFacts(node_id=node.id, name=node.name, status="down", error=error)

    return _parse_facts(node, completed.stdout)


def _parse_facts(node: Node, output: str) -> NodeFacts:
    values: dict[str, str] = {}
    interfaces: list[str] = []
    routes: list[str] = []
    section: str | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line == "INTERFACES_BEGIN":
            section = "interfaces"
            continue
        if line == "INTERFACES_END":
            section = None
            continue
        if line == "ROUTES_BEGIN":
            section = "routes"
            continue
        if line == "ROUTES_END":
            section = None
            continue

        if section == "interfaces" and line:
            interfaces.append(line)
            continue
        if section == "routes" and line:
            routes.append(line)
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    return NodeFacts(
        node_id=node.id,
        name=node.name,
        status="up",
        hostname=values.get("HOSTNAME") or None,
        kernel=values.get("KERNEL") or None,
        os=values.get("OS") or None,
        public_ip=values.get("PUBLIC_IP") or None,
        ip_forward=values.get("IP_FORWARD") or None,
        docker=values.get("DOCKER") or None,
        wireguard=values.get("WIREGUARD") or None,
        interfaces=interfaces,
        routes=routes,
    )
