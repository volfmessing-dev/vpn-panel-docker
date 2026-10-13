export type NodeRole = "mikrotik" | "ru_cloud" | "amnezia_exit";

export interface NodeRecord {
  id: number;
  name: string;
  role: NodeRole;
  host: string;
  ssh_user: string | null;
  ssh_port: number;
}

export type NodeUplinkType = "none" | "wireguard" | "amneziawg";

export interface NodeCreatePayload extends Omit<NodeRecord, "id"> {
  uplink_type?: NodeUplinkType;
}

export interface NodeCreateResult {
  node: NodeRecord;
  created_tunnel: TunnelRecord | null;
  apply_result: AmneziaWGApplyResult | null;
  apply_error: string | null;
}

export interface TopologyLink {
  source: string;
  target: string;
  type: string;
  status: string;
}

export interface Topology {
  nodes: Array<{ id: string; role: string; host: string }>;
  links: TopologyLink[];
}

export interface NodeHealth {
  checked_at?: string | null;
  node_id: number;
  name: string;
  status: "up" | "down" | "unknown";
  check: string;
  message: string;
  latency_ms: number | null;
}

export interface NodeFacts {
  checked_at?: string | null;
  node_id: number;
  name: string;
  status: "up" | "down" | "unsupported";
  hostname: string | null;
  kernel: string | null;
  os: string | null;
  public_ip: string | null;
  ip_forward: string | null;
  docker: string | null;
  wireguard: string | null;
  interfaces: string[];
  routes: string[];
  error: string | null;
}

export interface CloudTunnelPeer {
  public_key: string;
  endpoint: string | null;
  allowed_ips: string[];
  latest_handshake: number | null;
  transfer_rx: number | null;
  transfer_tx: number | null;
  persistent_keepalive: string | null;
}

export interface CloudTunnelInterface {
  name: string;
  display_name: string;
  location: string | null;
  kind: string;
  public_key: string | null;
  listen_port: number | null;
  fwmark: string | null;
  addresses: string[];
  flags: string[];
  operstate: string | null;
  mtu: number | null;
  routes: string[];
  peers: CloudTunnelPeer[];
}

export interface CloudTunnelSnapshot {
  node_id: number;
  node_name: string;
  host: string;
  status: "up" | "down";
  interfaces: CloudTunnelInterface[];
  rules: string[];
  error: string | null;
}

export interface TunnelRecord {
  id: number;
  name: string;
  type: "wireguard" | "amneziawg";
  source_node_id: number;
  target_node_id: number;
  tunnel_cidr: string;
  listen_port: number;
  lan_cidr: string;
  enabled: boolean;
  source_public_key: string | null;
  target_public_key: string | null;
  applied_at: string | null;
}

export interface TunnelPreview {
  tunnel_id: number;
  name: string;
  type: "wireguard" | "amneziawg";
  tunnel_network: string;
  source_tunnel_ip: string;
  target_tunnel_ip: string;
  gateway: string;
  endpoint: string;
  mikrotik_allowed_ips: string;
  ru_cloud_config: string;
  mikrotik_config: string;
  mikrotik_commands: string;
  ru_cloud_config_path: string | null;
  exit_config: string | null;
  exit_config_path: string | null;
  interface_name: string | null;
  ru_cloud_commands: string | null;
  exit_commands: string | null;
  notes: string[];
}

export interface TunnelApplyResult {
  tunnel_id: number;
  name: string;
  status: "applied" | "failed";
  message: string;
  ru_cloud_config_path: string;
  source_public_key: string;
  target_public_key: string;
}

export interface AmneziaWGApplyResult {
  tunnel_id: number;
  name: string;
  status: "applied" | "failed";
  message: string;
  interface_name: string;
  ru_cloud_config_path: string;
  exit_config_path: string;
  exit_egress_interface: string;
  source_public_key: string;
  target_public_key: string;
}

export type RoutingPolicySource = "wg_users_bypass" | "wg_users_default" | "wg_mikrotik";
export type RoutingPolicyTarget = "tunnel" | "direct";

export interface RoutingPolicyRecord {
  id: number;
  source: RoutingPolicySource;
  target: RoutingPolicyTarget;
  target_tunnel_id: number | null;
  direct_interface: string | null;
  enabled: boolean;
  priority: number;
  applied_at: string | null;
  target_tunnel: TunnelRecord | null;
  resolved_interface: string | null;
}

export interface RoutingPolicySnapshot {
  policies: RoutingPolicyRecord[];
  available_tunnels: TunnelRecord[];
}

export interface RoutingPolicyPreview {
  source: RoutingPolicySource;
  resolved_interface: string | null;
  commands: string[];
  warnings: string[];
}

export interface RoutingPolicyApplyResult {
  status: "applied" | "failed";
  message: string;
  applied_users: number;
  reapplied_tunnel_ids: number[];
  warnings: string[];
}

export interface VpnUserRecord {
  id: number;
  name: string;
  client_ip: string;
  public_key: string;
  enabled: boolean;
  applied_at: string | null;
  latest_handshake: number | null;
  latest_handshake_at: string | null;
}

export interface VpnUserConfig {
  user_id: number;
  name: string;
  filename: string;
  config: string;
}

export interface VpnUserApplyResult {
  status: "applied" | "failed";
  message: string;
  applied_users: number;
}

export interface VpnBypassStatus {
  status: "up" | "down";
  domains: string[];
  ips: string[];
  rules: string[];
  mangle: string[];
  error: string | null;
}
