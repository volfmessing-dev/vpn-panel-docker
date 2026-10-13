import { ArrowRight, Cable, ChevronRight, Clock3, Globe2, ListFilter, Router, Server, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import type { CloudTunnelInterface, CloudTunnelSnapshot, NodeRecord, TopologyLink, TunnelRecord, VpnBypassStatus, VpnUserRecord } from "../types/api";

interface Props {
  nodes: NodeRecord[]; links: TopologyLink[]; tunnels: TunnelRecord[]; users: VpnUserRecord[];
  bypass: VpnBypassStatus | null; cloudTunnels: CloudTunnelSnapshot | null;
  now: number; hasData: boolean; stale: boolean;
  onNavigate: (page: "nodes" | "cloud-tunnels" | "users" | "bypass-list" | "topology" | "traffic-policy") => void;
}

function handshakeAge(item: CloudTunnelInterface | undefined, now: number): number | null {
  const latest = Math.max(0, ...(item?.peers.map((peer) => peer.latest_handshake ?? 0) ?? []));
  return latest ? Math.max(0, Math.floor(now / 1000 - latest)) : null;
}
function ageLabel(age: number | null) {
  return age === null ? "Нет handshake" : age < 60 ? `${age} сек. назад` : age < 3600 ? `${Math.floor(age / 60)} мин. назад` : `${Math.floor(age / 3600)} ч. назад`;
}

export function Dashboard({ nodes, links, tunnels, users, bypass, cloudTunnels, now, hasData, stale, onNavigate }: Props) {
  // Only the route in the exit table identifies the selected exit; an UP interface alone does not.
  const defaultRoute = cloudTunnels?.interfaces.flatMap((item) => item.routes).find((route) => /^default\b/.test(route.trim()) && /\btable vpn_panel_exit\b/.test(route));
  const exitName = defaultRoute?.match(/\bdev\s+(\S+)/)?.[1];
  const exit = cloudTunnels?.interfaces.find((item) => item.name === exitName);
  const home = cloudTunnels?.interfaces.find((item) => item.name === "wg-ru-cloud");
  const exitAge = handshakeAge(exit, now);
  const userKeys = new Set(users.map((user) => user.public_key));
  const homeAge = handshakeAge(home ? { ...home, peers: home.peers.filter((peer) => !userKeys.has(peer.public_key)) } : undefined, now);
  const peerByKey = new Map((home?.peers ?? []).map((peer) => [peer.public_key, peer]));
  const observedUsers = users.map((user) => ({ ...user, latest_handshake: peerByKey.get(user.public_key)?.latest_handshake ?? user.latest_handshake }));
  const exitActive = cloudTunnels?.status === "up" && Boolean(exit?.flags.includes("LOWER_UP")) && exitAge !== null && exitAge < 180;
  const activeUsers = observedUsers.filter((user) => user.enabled && user.latest_handshake && now / 1000 - user.latest_handshake < 180).length;
  const enabledUsers = users.filter((user) => user.enabled).length;
  const latestUsers = [...observedUsers].filter((user) => user.latest_handshake).sort((a, b) => (b.latest_handshake ?? 0) - (a.latest_handshake ?? 0)).slice(0, 4);
  const exitNode = nodes.find((node) => node.role === "amnezia_exit" && exit?.peers.some((peer) => peer.endpoint?.startsWith(`${node.host}:`)));
  const exitLabel = exitNode?.name || exit?.display_name || exitName || "Выход не определён";
  const status = !hasData ? "Ожидаем данные" : stale ? "Данные устарели" : exitActive ? "Туннель активен" : "Требует проверки";
  const tone = !hasData || stale ? "neutral" : exitActive ? "up" : "warning";
  const recent = (age: number | null) => !hasData || stale ? "Нет свежих данных" : age !== null && age < 180 ? "Свежий handshake" : "Нет свежего handshake";

  return <section className="dashboard-stack">
    <div className="overview-intro"><div><h3>Сеть под контролем</h3><p>Активный маршрут и последние данные подключений.</p></div><span className={`status-pill ${tone}`}><span className="status-dot" />{status}</span></div>
    <div className="dashboard-grid">
      <Metric icon={<Globe2 size={19} />} label="Выходной туннель" value={hasData ? exit?.name || "—" : "—"} detail={hasData ? status : "Данные ещё не получены"} onClick={() => onNavigate("cloud-tunnels")} />
      <Metric icon={<Clock3 size={19} />} label="Последний handshake" value={hasData && exitAge !== null ? exitAge < 60 ? `${exitAge} сек.` : exitAge < 3600 ? `${Math.floor(exitAge / 60)} мин.` : `${Math.floor(exitAge / 3600)} ч.` : "—"} detail="Выходной туннель · давность" onClick={() => onNavigate("cloud-tunnels")} />
      <Metric icon={<UserRound size={19} />} label="Пользователи онлайн" value={hasData ? String(activeUsers) : "—"} detail={hasData ? `Из ${enabledUsers} включённых · handshake < 3 мин.` : "Данные ещё не получены"} onClick={() => onNavigate("users")} />
      <Metric icon={<ListFilter size={19} />} label="Адреса обхода" value={hasData ? String(bypass?.ips.length ?? 0) : "—"} detail={hasData ? `${bypass?.domains.length ?? 0} доменов · ${bypass?.status === "up" ? "ipset загружен" : "ipset недоступен"}` : "Данные ещё не получены"} onClick={() => onNavigate("bypass-list")} />
    </div>
    <div className="panel route-panel">
      <div className="panel-header"><div><span className="section-kicker">МАРШРУТ ОБХОДА</span><h3>От домашней сети до выхода</h3></div><button className="text-button inline-button" onClick={() => onNavigate("topology")}>Схема сети<ChevronRight size={16} /></button></div>
      <div className="route-flow">
        <button className="route-node" onClick={() => onNavigate("nodes")}><span className="route-icon"><Router size={23} /></span><span className="route-role">Домашняя сеть</span><strong>{nodes.find((node) => node.role === "mikrotik")?.name || "MikroTik"}</strong><span className="route-address">{nodes.find((node) => node.role === "mikrotik")?.host || "—"}</span><span className={`route-health ${!stale && hasData && homeAge !== null && homeAge < 180 ? "up" : "neutral"}`}><span className="status-dot" />{recent(homeAge)}</span></button>
        <div className="route-connector"><span>WireGuard</span><ArrowRight size={24} /></div>
        <button className="route-node gateway" onClick={() => onNavigate("cloud-tunnels")}><span className="route-icon"><Server size={23} /></span><span className="route-role">Облачный шлюз</span><strong>{cloudTunnels?.node_name || "RU_Cloud"}</strong><span className="route-address">{cloudTunnels?.host || "—"}</span><span className={`route-health ${!hasData || stale ? "neutral" : cloudTunnels?.status === "up" ? "up" : "warning"}`}><span className="status-dot" />{!hasData || stale ? "Нет свежих данных" : cloudTunnels?.status === "up" ? "Интерфейсы получены" : "Проверка недоступна"}</span></button>
        <div className="route-connector"><span>AmneziaWG</span><ArrowRight size={24} /></div>
        <button className="route-node" onClick={() => onNavigate("cloud-tunnels")}><span className="route-icon"><Globe2 size={23} /></span><span className="route-role">Выход в интернет</span><strong>{hasData ? exitLabel : "Ожидаем данные"}</strong><span className="route-address">{exit?.peers[0]?.endpoint || "—"}</span><span className={`route-health ${tone}`}><span className="status-dot" />{recent(exitAge)}</span></button>
      </div>
      <p className="route-note">Статусы основаны на данных шлюза и handshake. Доступность сайтов через выход отдельно не проверяется.</p>
    </div>
    <div className="overview-columns">
      <div className="panel"><div className="panel-header"><div><span className="section-kicker">ПОДКЛЮЧЕНИЯ</span><h3>Последняя активность</h3></div><button className="text-button inline-button" onClick={() => onNavigate("users")}>Все пользователи<ChevronRight size={16} /></button></div>
        {latestUsers.length ? <div className="activity-list">{latestUsers.map((user) => <div className="activity-row" key={user.id}><span className="user-avatar"><UserRound size={18} /></span><div><strong>{user.name}</strong><span>{user.client_ip}</span></div><span className="activity-time">{user.enabled ? ageLabel(Math.max(0, Math.floor(now / 1000 - (user.latest_handshake ?? 0)))) : "Отключён"}</span></div>)}</div> : <div className="empty-state"><UserRound size={25} /><p>{hasData ? "Пока нет данных о подключениях" : "Активность появится после загрузки"}</p></div>}
      </div>
      <div className="panel"><div className="panel-header"><div><span className="section-kicker">ТРАФИК</span><h3>Направления маршрутизации</h3></div><Cable size={20} className="muted-icon" /></div><div className="routing-summary"><div><span>Домашняя сеть</span><strong>Маркированный трафик → выход</strong></div><div><span>Пользователи WireGuard</span><strong>Обход → выход · остальное → RU</strong></div></div><button className="text-button inline-button" onClick={() => onNavigate("traffic-policy")}>Открыть правила<ChevronRight size={16} /></button><p className="route-note">Схема назначений; актуальные правила — в разделе «Правила трафика».</p></div>
    </div>
    <div className="inventory-strip"><span>Конфигурация</span><span><strong>{hasData ? nodes.length : "—"}</strong> узлов</span><span><strong>{hasData ? links.length : "—"}</strong> связей</span><span><strong>{hasData ? `${tunnels.filter((tunnel) => tunnel.applied_at).length}/${tunnels.length}` : "—"}</strong> туннелей применено</span><span><strong>{hasData ? users.length : "—"}</strong> пользователей</span></div>
  </section>;
}
function Metric({ icon, label, value, detail, onClick }: { icon: ReactNode; label: string; value: string; detail: string; onClick: () => void }) {
  return <button className="metric" onClick={onClick}><span className="metric-heading">{label}<span className="metric-icon">{icon}</span></span><strong>{value}</strong><span className="metric-detail">{detail}</span></button>;
}
