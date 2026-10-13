import ipaddress

from app.models.node import Node
from app.models.tunnel import Tunnel
from app.schemas.tunnel import TunnelPreview
from app.services.wireguard.exit_policy import exit_interface_name


def build_wireguard_preview(tunnel: Tunnel, source: Node, target: Node) -> TunnelPreview:
    network = ipaddress.ip_network(tunnel.tunnel_cidr, strict=False)
    hosts = list(network.hosts())
    if len(hosts) < 2:
        raise ValueError("Tunnel CIDR must provide at least two host addresses")

    target_ip = hosts[0]
    source_ip = hosts[1]

    target_private = tunnel.target_private_key or f"<{target.name}_private_key>"
    source_public = tunnel.source_public_key or f"<{source.name}_public_key>"
    source_private = tunnel.source_private_key or "<mikrotik_private_key>"
    target_public = tunnel.target_public_key or f"<{target.name}_public_key>"
    endpoint = f"{target.host}:{tunnel.listen_port}"
    mikrotik_allowed_ips = "0.0.0.0/0"

    ru_cloud_config = f"""# Dry-run only. Apply RU_Cloud writes this to /etc/wireguard/wg-ru-cloud.conf.
[Interface]
Address = {target_ip}/{network.prefixlen}
ListenPort = {tunnel.listen_port}
PrivateKey = {target_private}
PostUp = ip rule add from {tunnel.lan_cidr} table vpn_panel_exit priority 12031 2>/dev/null || true
PostUp = ip rule add from {source_ip}/32 table vpn_panel_exit priority 12032 2>/dev/null || true
PostUp = ip route replace default dev awg4 table vpn_panel_exit
PostUp = iptables -t nat -C POSTROUTING -s {tunnel.lan_cidr} -o awg4 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s {tunnel.lan_cidr} -o awg4 -j MASQUERADE
PostUp = iptables -t nat -C POSTROUTING -s {source_ip}/32 -o awg4 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s {source_ip}/32 -o awg4 -j MASQUERADE
PostDown = ip rule del from {tunnel.lan_cidr} table vpn_panel_exit priority 12031 2>/dev/null || true
PostDown = ip rule del from {source_ip}/32 table vpn_panel_exit priority 12032 2>/dev/null || true
PostDown = iptables -t nat -D POSTROUTING -s {tunnel.lan_cidr} -o awg4 -j MASQUERADE 2>/dev/null || true
PostDown = iptables -t nat -D POSTROUTING -s {source_ip}/32 -o awg4 -j MASQUERADE 2>/dev/null || true

[Peer]
PublicKey = {source_public}
AllowedIPs = {source_ip}/32, {tunnel.lan_cidr}
"""

    mikrotik_config = f"""# MikroTik WireGuard peer settings.
# Use these values on RouterOS or keep the commands below as the source of truth.
[Interface]
Name = wg-ru-cloud
Address = {source_ip}/{network.prefixlen}
ListenPort = {tunnel.listen_port}
PrivateKey = {source_private}

[Peer]
PublicKey = {target_public}
Endpoint = {endpoint}
AllowedIPs = {mikrotik_allowed_ips}
PersistentKeepalive = 25

[Routing]
Table = to-ru-cloud
Gateway = {target_ip}
BypassSourceCIDR = {tunnel.lan_cidr}
BypassDstAddressList = bypass
"""

    mikrotik_commands = f"""/interface wireguard
add name=wg-ru-cloud listen-port={tunnel.listen_port} private-key="{source_private}"

/ip address
add address={source_ip}/{network.prefixlen} interface=wg-ru-cloud

/interface wireguard peers
add interface=wg-ru-cloud public-key="{target_public}" endpoint-address={target.host} endpoint-port={tunnel.listen_port} allowed-address=0.0.0.0/0 persistent-keepalive=25s

/routing table
add name=to-ru-cloud fib

/ip firewall mangle
add chain=prerouting src-address={tunnel.lan_cidr} dst-address-list=bypass action=mark-routing new-routing-mark=to-ru-cloud passthrough=no

/ip route
add dst-address=0.0.0.0/0 gateway=wg-ru-cloud routing-table=to-ru-cloud
"""

    return TunnelPreview(
        tunnel_id=tunnel.id,
        name=tunnel.name,
        type=tunnel.type,
        tunnel_network=str(network),
        source_tunnel_ip=str(source_ip),
        target_tunnel_ip=str(target_ip),
        gateway=str(target_ip),
        endpoint=endpoint,
        mikrotik_allowed_ips=mikrotik_allowed_ips,
        ru_cloud_config=ru_cloud_config,
        mikrotik_config=mikrotik_config,
        mikrotik_commands=mikrotik_commands,
        notes=[
            "Preview only unless Apply RU_Cloud has been pressed.",
            f"Tunnel network is normalized to {network}.",
            f"MikroTik gateway for this tunnel is {target_ip}.",
            f"{target.name} uses the first usable tunnel IP: {target_ip}.",
            f"{source.name} uses the second usable tunnel IP: {source_ip}.",
            f"Open UDP/{tunnel.listen_port} on {target.name}.",
            "After apply, verify latest handshake on both peers.",
        ],
    )


def build_amneziawg_preview(tunnel: Tunnel, source: Node, target: Node) -> TunnelPreview:
    network = ipaddress.ip_network(tunnel.tunnel_cidr, strict=False)
    hosts = list(network.hosts())
    if len(hosts) < 2:
        raise ValueError("Tunnel CIDR must provide at least two host addresses")

    ru_ip = hosts[0]
    exit_ip = hosts[1]
    interface = exit_interface_name(tunnel, target.name)
    ru_private = tunnel.source_private_key or f"<{source.name}_private_key>"
    ru_public = tunnel.source_public_key or f"<{source.name}_public_key>"
    exit_private = tunnel.target_private_key or f"<{target.name}_private_key>"
    exit_public = tunnel.target_public_key or f"<{target.name}_public_key>"
    endpoint = f"{target.host}:{tunnel.listen_port}"
    ru_path = f"/etc/amnezia/{interface}.conf"
    exit_path = f"/etc/amnezia/{interface}-exit.conf"

    ru_cloud_config = f"""# Dry-run only. Apply AWG will write this on {source.name}.
[Interface]
Address = {ru_ip}/{network.prefixlen}
PrivateKey = {ru_private}
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
PublicKey = {exit_public}
Endpoint = {endpoint}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""

    exit_config = f"""# Dry-run only. Apply AWG will write this on {target.name}.
[Interface]
Address = {exit_ip}/{network.prefixlen}
ListenPort = {tunnel.listen_port}
PrivateKey = {exit_private}
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
PostUp = iptables -t nat -C POSTROUTING -s {network} -o <exit-interface> -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s {network} -o <exit-interface> -j MASQUERADE
PostDown = true

[Peer]
PublicKey = {ru_public}
AllowedIPs = {ru_ip}/32
"""

    ru_commands = f"""sudo mkdir -p /etc/amnezia
sudo install -m 600 <generated> {ru_path}
sudo systemctl enable --now awg-quick@{interface}.service
sudo awg show {interface}
"""

    exit_commands = f"""sudo mkdir -p /etc/amnezia
sudo install -m 600 <generated> {exit_path}
sudo systemctl enable --now awg-quick@{interface}-exit.service
sudo awg show {interface}-exit
"""

    return TunnelPreview(
        tunnel_id=tunnel.id,
        name=tunnel.name,
        type=tunnel.type,
        tunnel_network=str(network),
        source_tunnel_ip=str(ru_ip),
        target_tunnel_ip=str(exit_ip),
        gateway=str(exit_ip),
        endpoint=endpoint,
        mikrotik_allowed_ips="",
        ru_cloud_config=ru_cloud_config,
        mikrotik_config="",
        mikrotik_commands="",
        ru_cloud_config_path=ru_path,
        exit_config=exit_config,
        exit_config_path=exit_path,
        interface_name=interface,
        ru_cloud_commands=ru_commands,
        exit_commands=exit_commands,
        notes=[
            "Preview only; no files are written by this endpoint.",
            f"RU_Cloud uses {ru_ip}; {target.name} uses {exit_ip}.",
            f"Open UDP/{tunnel.listen_port} on {target.name}.",
            f"Expected RU_Cloud interface name is {interface}.",
            "Exit NAT egress interface is not auto-detected yet; verify before apply.",
        ],
    )
