import type {
  AmneziaWGApplyResult,
  CloudTunnelSnapshot,
  NodeFacts,
  NodeHealth,
  NodeCreatePayload,
  NodeCreateResult,
  NodeRecord,
  RoutingPolicyApplyResult,
  RoutingPolicyPreview,
  RoutingPolicyRecord,
  RoutingPolicySnapshot,
  RoutingPolicySource,
  Topology,
  TunnelApplyResult,
  TunnelPreview,
  TunnelRecord,
  VpnUserApplyResult,
  VpnBypassStatus,
  VpnUserConfig,
  VpnUserRecord
} from "../types/api";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options
  });

  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? `: ${body.detail}` : "";
    } catch {
      detail = "";
    }
    throw new Error(`Request failed: ${response.status}${detail}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function getNodes(): Promise<NodeRecord[]> {
  return request<NodeRecord[]>("/api/nodes");
}

export function createNode(payload: NodeCreatePayload): Promise<NodeCreateResult> {
  return request<NodeCreateResult>("/api/nodes", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateNode(id: number, payload: Omit<NodeRecord, "id">): Promise<NodeRecord> {
  return request<NodeRecord>(`/api/nodes/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function deleteNode(id: number): Promise<void> {
  await request<void>(`/api/nodes/${id}`, { method: "DELETE" });
}

export function getTopology(): Promise<Topology> {
  return request<Topology>("/api/topology");
}

export function getConfigPreview(): Promise<{ config: string }> {
  return request<{ config: string }>("/api/config/preview");
}

export function getNodeHealth(): Promise<NodeHealth[]> {
  return request<NodeHealth[]>("/api/nodes/health");
}

export function getNodeFacts(): Promise<NodeFacts[]> {
  return request<NodeFacts[]>("/api/nodes/facts");
}

export function getActiveCloudTunnels(): Promise<CloudTunnelSnapshot> {
  return request<CloudTunnelSnapshot>("/api/cloud/tunnels/active");
}

export function getRoutingPolicies(): Promise<RoutingPolicySnapshot> {
  return request<RoutingPolicySnapshot>("/api/routing-policies");
}

export function getRoutingPolicyPreview(): Promise<RoutingPolicyPreview[]> {
  return request<RoutingPolicyPreview[]>("/api/routing-policies/preview");
}

export function applyRoutingPolicies(): Promise<RoutingPolicyApplyResult> {
  return request<RoutingPolicyApplyResult>("/api/routing-policies/apply", { method: "POST" });
}

export function updateRoutingPolicy(
  source: RoutingPolicySource,
  payload: Pick<RoutingPolicyRecord, "target" | "target_tunnel_id" | "direct_interface" | "enabled">
): Promise<RoutingPolicyRecord> {
  return request<RoutingPolicyRecord>(`/api/routing-policies/${source}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function getTunnels(): Promise<TunnelRecord[]> {
  return request<TunnelRecord[]>("/api/tunnels");
}

export function createTunnel(payload: Omit<TunnelRecord, "id">): Promise<TunnelRecord> {
  return request<TunnelRecord>("/api/tunnels", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateTunnel(id: number, payload: Omit<TunnelRecord, "id">): Promise<TunnelRecord> {
  return request<TunnelRecord>(`/api/tunnels/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function deleteTunnel(id: number): Promise<void> {
  await request<void>(`/api/tunnels/${id}`, { method: "DELETE" });
}

export function getTunnelPreview(id: number): Promise<TunnelPreview> {
  return request<TunnelPreview>(`/api/tunnels/${id}/preview`);
}

export function generateTunnelKeys(id: number): Promise<TunnelRecord> {
  return request<TunnelRecord>(`/api/tunnels/${id}/keys`, { method: "POST" });
}

export function applyRuCloudTunnel(id: number): Promise<TunnelApplyResult> {
  return request<TunnelApplyResult>(`/api/tunnels/${id}/apply/ru-cloud`, { method: "POST" });
}

export function applyAmneziaWGTunnel(id: number): Promise<AmneziaWGApplyResult> {
  return request<AmneziaWGApplyResult>(`/api/tunnels/${id}/apply/awg`, { method: "POST" });
}

export function getVpnUsers(): Promise<VpnUserRecord[]> {
  return request<VpnUserRecord[]>("/api/users");
}

export function createVpnUser(payload: Pick<VpnUserRecord, "name" | "enabled">): Promise<VpnUserRecord> {
  return request<VpnUserRecord>("/api/users", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateVpnUser(id: number, payload: Pick<VpnUserRecord, "name" | "enabled">): Promise<VpnUserRecord> {
  return request<VpnUserRecord>(`/api/users/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function deleteVpnUser(id: number): Promise<void> {
  await request<void>(`/api/users/${id}`, { method: "DELETE" });
}

export function applyVpnUsers(): Promise<VpnUserApplyResult> {
  return request<VpnUserApplyResult>("/api/users/apply", { method: "POST" });
}

export function getVpnBypassStatus(): Promise<VpnBypassStatus> {
  return request<VpnBypassStatus>("/api/users/bypass");
}

export function refreshVpnBypass(): Promise<VpnUserApplyResult> {
  return request<VpnUserApplyResult>("/api/users/bypass/refresh", { method: "POST" });
}

export function updateVpnBypassDomains(domains: string[]): Promise<Pick<VpnBypassStatus, "domains">> {
  return request<Pick<VpnBypassStatus, "domains">>("/api/users/bypass/domains", {
    method: "PUT",
    body: JSON.stringify({ domains })
  });
}

export function getVpnUserConfig(id: number): Promise<VpnUserConfig> {
  return request<VpnUserConfig>(`/api/users/${id}/config`);
}

export function vpnUserDownloadUrl(id: number): string {
  return `${API_BASE_URL}/api/users/${id}/download`;
}

export function vpnUserQrUrl(id: number): string {
  return `${API_BASE_URL}/api/users/${id}/qr`;
}

export function checkSingleNode(id: number): Promise<NodeHealth> {
  return request<NodeHealth>(`/api/nodes/${id}/health`);
}

export function collectSingleNodeFacts(id: number): Promise<NodeFacts> {
  return request<NodeFacts>(`/api/nodes/${id}/facts`);
}
