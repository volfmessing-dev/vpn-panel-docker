import type { CloudTunnelSnapshot, NodeRecord, TunnelRecord } from "../types/api";

export interface NodeTunnelStatus {
  key: string;
  label: string;
  tone: "up" | "warning" | "neutral";
  title: string;
  detail: string;
}

/** Match the remote peer, never the latest handshake across a shared interface. */
export function nodeTunnelStatuses(
  node: NodeRecord, nodes: NodeRecord[], tunnels: TunnelRecord[],
  snapshot: CloudTunnelSnapshot | null, now: number, hasData: boolean, stale: boolean,
): NodeTunnelStatus[] {
  if (node.role === "ru_cloud") {
    const relatedIds = new Set(tunnels.filter(t => t.source_node_id === node.id || t.target_node_id === node.id)
      .map(t => t.source_node_id === node.id ? t.target_node_id : t.source_node_id));
    return nodes.filter(n => relatedIds.has(n.id) && n.role !== "ru_cloud" && !/^Archived(_|$)/i.test(n.name))
      .flatMap(remote => nodeTunnelStatuses(remote, nodes, tunnels, snapshot, now, hasData, stale)
        .map(result => ({ ...result, title: `Туннель к ${remote.name}` })));
  }
  const title = "Туннель к шлюзу";
  const unknown = (detail: string): NodeTunnelStatus[] => [{ key: String(node.id), title, tone: "neutral", label: "Нет свежих данных", detail }];
  if (!hasData || !snapshot || snapshot.status !== "up" || stale) return unknown(stale ? "Снимок шлюза устарел" : "Данные шлюза недоступны");
  const related = tunnels.filter(t => t.source_node_id === node.id || t.target_node_id === node.id);
  const keys = related.map(t => t.source_node_id === node.id ? t.source_public_key : t.target_public_key).filter(Boolean);
  const matches = snapshot.interfaces.flatMap(item => item.peers.filter(peer => {
    const endpointHost = peer.endpoint?.slice(0, peer.endpoint.lastIndexOf(":")).replace(/^\[|\]$/g, "");
    return keys.includes(peer.public_key) || endpointHost === node.host || peer.allowed_ips.includes(`${node.host}/32`) || peer.allowed_ips.includes(`${node.host}/128`);
  }).map(peer => ({ item, peer })));
  if (!matches.length) return unknown("Peer устройства не найден на шлюзе");
  return matches.map(({ item, peer }) => {
    const age = peer.latest_handshake && peer.latest_handshake > 0 ? Math.max(0, Math.floor(now / 1000 - peer.latest_handshake)) : null;
    const recent = age !== null && age < 180;
    const raised = item.flags.includes("LOWER_UP");
    const label = !raised ? "Интерфейс не поднят" : recent ? "Туннель активен" : "Нет свежего handshake";
    const handshake = age === null ? "Handshake отсутствует" : `Handshake ${age < 60 ? `${age} сек.` : age < 3600 ? `${Math.floor(age / 60)} мин.` : `${Math.floor(age / 3600)} ч.`} назад`;
    return { key: `${node.id}-${item.name}-${peer.public_key}`, title, tone: raised && recent ? "up" : "warning", label, detail: `${item.name} · ${handshake}` };
  });
}
