import json
import shlex

from app.models.node import Node
from app.schemas.cloud_tunnel import CloudTunnelInterface, CloudTunnelPeer, CloudTunnelSnapshot
from app.services.deployment.ssh import ssh_command


def collect_active_cloud_tunnels(node: Node) -> CloudTunnelSnapshot:
    command = """
set -u
printf '__IP_ADDR__\\n'
ip -j addr show
printf '\\n__WG_DUMP__\\n'
sudo wg show all dump 2>/dev/null || true
printf '\\n__AWG_DUMP__\\n'
sudo awg show all dump 2>/dev/null || true
printf '\\n__ROUTES__\\n'
ip route show table all
printf '\\n__RULES__\\n'
ip rule show
"""
    completed = ssh_command(node, command, timeout=12)
    if completed.returncode != 0:
        return CloudTunnelSnapshot(
            node_id=node.id,
            node_name=node.name,
            host=node.host,
            status="down",
            interfaces=[],
            rules=[],
            error=completed.stderr.strip() or completed.stdout.strip() or f"ssh exited with {completed.returncode}",
        )

    sections = _split_sections(completed.stdout)
    address_data = _parse_ip_addr(sections.get("IP_ADDR", "[]"))
    routes = [line for line in sections.get("ROUTES", "").splitlines() if line.strip()]
    rules = [line for line in sections.get("RULES", "").splitlines() if line.strip()]

    interfaces: dict[str, CloudTunnelInterface] = {}
    _merge_dump(interfaces, sections.get("WG_DUMP", ""), "wireguard")
    _merge_dump(interfaces, sections.get("AWG_DUMP", ""), "amneziawg")

    for name, details in address_data.items():
        if not (name.startswith("wg") or name.startswith("awg")):
            continue
        if name not in interfaces:
            interfaces[name] = CloudTunnelInterface(
                name=name,
                display_name=_display_name(name),
                location=_location(name),
                kind="unknown",
                public_key=None,
                listen_port=None,
                fwmark=None,
                addresses=[],
                flags=[],
                operstate=None,
                mtu=None,
                routes=[],
                peers=[],
            )

        current = interfaces[name]
        interfaces[name] = current.model_copy(
            update={
                "addresses": details["addresses"],
                "flags": details["flags"],
                "operstate": details["operstate"],
                "mtu": details["mtu"],
                "routes": [route for route in routes if f" dev {shlex.quote(name)}" in route or f" dev {name}" in route],
            }
        )

    active = sorted(
        interfaces.values(),
        key=lambda item: (0 if "LOWER_UP" in item.flags else 1, item.name),
    )

    return CloudTunnelSnapshot(
        node_id=node.id,
        node_name=node.name,
        host=node.host,
        status="up",
        interfaces=active,
        rules=rules,
        error=None,
    )


def _split_sections(output: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in output.splitlines():
        if line.startswith("__") and line.endswith("__"):
            current = line.strip("_")
            sections[current] = []
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def _parse_ip_addr(raw: str) -> dict[str, dict[str, object]]:
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return {}

    result: dict[str, dict[str, object]] = {}
    for item in items:
        name = item.get("ifname")
        if not isinstance(name, str):
            continue
        addresses = []
        for addr in item.get("addr_info", []):
            local = addr.get("local")
            prefix = addr.get("prefixlen")
            family = addr.get("family")
            if family == "inet" and local and prefix is not None:
                addresses.append(f"{local}/{prefix}")
        result[name] = {
            "addresses": addresses,
            "flags": item.get("flags", []),
            "operstate": item.get("operstate"),
            "mtu": item.get("mtu"),
        }
    return result


def _merge_dump(interfaces: dict[str, CloudTunnelInterface], dump: str, kind: str) -> None:
    for line in dump.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 5:
            continue

        name = fields[0]
        is_interface = (kind == "wireguard" and len(fields) == 5) or (kind == "amneziawg" and len(fields) > 15)
        if is_interface:
            public_key = fields[2] if len(fields) > 2 and fields[2] != "(none)" else None
            listen_port = _int_or_none(fields[3] if len(fields) > 3 else None)
            fwmark = fields[-1] if kind == "amneziawg" and len(fields) > 18 else (fields[4] if len(fields) > 4 else None)
            if fwmark == "off":
                fwmark = None
            existing = interfaces.get(name)
            interfaces[name] = CloudTunnelInterface(
                name=name,
                display_name=_display_name(name),
                location=_location(name),
                kind=kind,
                public_key=public_key,
                listen_port=listen_port,
                fwmark=fwmark,
                addresses=existing.addresses if existing else [],
                flags=existing.flags if existing else [],
                operstate=existing.operstate if existing else None,
                mtu=existing.mtu if existing else None,
                routes=existing.routes if existing else [],
                peers=existing.peers if existing else [],
            )
            continue

        if name not in interfaces:
            continue
        interface = interfaces[name]
        peer = _parse_peer(fields)
        interfaces[interface.name] = interface.model_copy(update={"peers": [*interface.peers, peer]})


def _parse_peer(fields: list[str]) -> CloudTunnelPeer:
    return CloudTunnelPeer(
        public_key=fields[1],
        endpoint=_none_if_empty(fields[3] if len(fields) > 3 else None),
        allowed_ips=_split_allowed(fields[4] if len(fields) > 4 else ""),
        latest_handshake=_int_or_none(fields[5] if len(fields) > 5 else None),
        transfer_rx=_int_or_none(fields[6] if len(fields) > 6 else None),
        transfer_tx=_int_or_none(fields[7] if len(fields) > 7 else None),
        persistent_keepalive=_none_if_empty(fields[8] if len(fields) > 8 else None),
    )


def _split_allowed(value: str) -> list[str]:
    if not value or value == "(none)":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _none_if_empty(value: str | None) -> str | None:
    if not value or value in {"(none)", "off"}:
        return None
    return value


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value and value != "off" else None
    except ValueError:
        return None


def _display_name(name: str) -> str:
    labels = {
        "wg-ru-cloud": "wg - mikrotik",
        "awg1": "awg - amsterdam",
        "awg3": "awg - estonia",
        "awg4": "awg - germany",
        "awg-cloud": "wg - estonia",
    }
    return labels.get(name, name)


def _location(name: str) -> str | None:
    locations = {
        "wg-ru-cloud": "mikrotik",
        "awg1": "amsterdam",
        "awg3": "estonia",
        "awg4": "germany",
        "awg-cloud": "estonia",
    }
    return locations.get(name)
