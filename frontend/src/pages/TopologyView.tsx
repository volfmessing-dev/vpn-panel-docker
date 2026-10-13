import { useState } from "react";
import { ArrowRight, Globe2, Router, Server, Network } from "lucide-react";
import { Modal } from "../components/Modal";
import type { CloudTunnelInterface, CloudTunnelSnapshot, NodeRecord, TunnelRecord, VpnUserRecord } from "../types/api";

interface Props {
  nodes: NodeRecord[];
  tunnels: TunnelRecord[];
  users: VpnUserRecord[];
  cloudTunnels: CloudTunnelSnapshot | null;
  now: number;
  hasData: boolean;
  stale: boolean;
}

export function TopologyView({ nodes, tunnels, users, cloudTunnels, now, hasData, stale }: Props) {
  const [selected, setSelected] = useState<number | null>(null);
  const current = nodes.filter(node => !/^(GER|EST)(_|$)/i.test(node.name));
  const links = tunnels.filter(tunnel => current.some(n => n.id === tunnel.source_node_id) && current.some(n => n.id === tunnel.target_node_id));
  const home = current.find(node => node.role === "mikrotik");
  const gateway = current.find(node => node.role === "ru_cloud");
  const defaultRoute = cloudTunnels?.interfaces.flatMap(item => item.routes).find(route => /^default\b/.test(route.trim()) && /\btable vpn_panel_exit\b/.test(route));
  const exitInterface = cloudTunnels?.interfaces.find(item => item.name === defaultRoute?.match(/\bdev\s+(\S+)/)?.[1]);
  const exit = current.find(node => node.role === "amnezia_exit" && exitInterface?.peers.some(peer => peer.endpoint?.startsWith(`${node.host}:`)));
  const homeInterface = cloudTunnels?.interfaces.find(item => item.name === "wg-ru-cloud");
  const userKeys = new Set(users.map(user => user.public_key));
  const age = (item: CloudTunnelInterface | undefined, homeLink = false) => {
    const peers = item?.peers.filter(peer => !homeLink || !userKeys.has(peer.public_key)) ?? [];
    const latest = Math.max(0, ...peers.map(peer => peer.latest_handshake ?? 0));
    return latest ? Math.max(0, Math.floor(now / 1000 - latest)) : null;
  };
  const state = (item: CloudTunnelInterface | undefined, homeLink = false) => {
    const seconds = age(item, homeLink);
    if (!hasData || stale || cloudTunnels?.status !== "up") return { tone: "neutral", label: "Нет свежих данных", detail: "Статус связи неизвестен" };
    if (!item) return { tone: "neutral", label: "Не определена", detail: "Интерфейс не найден" };
    return { tone: item.flags.includes("LOWER_UP") && seconds !== null && seconds < 180 ? "up" : "warning", label: seconds !== null && seconds < 180 && item.flags.includes("LOWER_UP") ? "Свежий handshake" : "Требует проверки", detail: seconds === null ? "Handshake отсутствует" : `Handshake: ${seconds < 60 ? `${seconds} сек.` : `${Math.floor(seconds / 60)} мин.`} назад` };
  };
  const homeState = state(homeInterface, true);
  const exitState = state(exitInterface);
  const selectedNode = current.find(node => node.id === selected);
  function connection(item: CloudTunnelInterface | undefined, homeLink: boolean) {
    const status = homeLink ? homeState : exitState;
    return <div className="network-connection"><span>{item?.kind === "amneziawg" || !homeLink ? "AmneziaWG" : "WireGuard"}</span><ArrowRight size={23} /><span className={`status-pill ${status.tone}`}>{status.label}</span><small>{item?.name ?? "—"}</small></div>;
  }
  function card(node: NodeRecord | undefined, title: string, icon: "home" | "cloud" | "exit") {
    return <button className={`network-node ${icon}`} disabled={!node} onClick={() => node && setSelected(node.id)}><span className="network-node-icon">{icon === "home" ? <Router size={28} /> : icon === "cloud" ? <Server size={28} /> : <Globe2 size={28} />}</span><span className="section-kicker">{title}</span><strong>{node?.name ?? (hasData ? "Не определён" : "Ожидаем данные")}</strong><code>{node?.host ?? "—"}</code><span className="network-node-link">{node ? "Подробнее о подключении" : "Нет подтверждённого узла"}</span></button>;
  }
  return <section className="network-page">
    <div className="users-intro"><div><h3>Маршрут вашей сети</h3><p>От домашнего маршрутизатора через облачный шлюз к выходу в интернет.</p></div><span className={`status-pill ${exit && exitState.tone === "up" ? "up" : "neutral"}`}><span className="status-dot" />{exit ? `Выход: ${exit.name}` : "Выход не подтверждён"}</span></div>
    <div className="panel network-map"><div className="network-map-header"><Network size={18} /><span>МАРШРУТ ОБХОДА</span></div><div className="network-flow">{card(home,"Домашняя сеть","home")}{connection(homeInterface,true)}{card(gateway,"Облачный шлюз","cloud")}{connection(exitInterface,false)}{card(exit,"Выход в интернет","exit")}</div><p className="network-caption">Выход определён по маршруту в таблице vpn_panel_exit. Handshake показывает активность туннеля; доступность сайтов отдельно не проверяется.</p></div>
    <div className="network-bottom"><div className="panel"><div className="panel-header"><h3>Связи текущей сети</h3><span className="status-pill neutral">{links.length}</span></div><div className="network-links">{links.map(tunnel => <div key={tunnel.id}><div><strong>{tunnel.name}</strong><p>{current.find(n => n.id === tunnel.source_node_id)?.name} → {current.find(n => n.id === tunnel.target_node_id)?.name}</p></div><span className={`status-pill ${tunnel.enabled ? "neutral" : "warning"}`}>{tunnel.enabled ? tunnel.applied_at ? "Конфигурация применена" : "Не применена" : "Выключен"}</span><details><summary>Параметры туннеля</summary><code>{tunnel.type} · {tunnel.tunnel_cidr} · UDP/{tunnel.listen_port}</code></details></div>)}</div>{!links.length ? <p className="network-caption">{hasData ? "Связей пока нет." : "Загружаем конфигурацию…"}</p> : null}</div><div className="panel network-legend"><h3>Как читать схему</h3><p><span className="status-dot network-good" /> Свежий handshake — менее 3 минут назад.</p><p><span className="status-dot network-warning" /> Нет свежего handshake или интерфейс не поднят.</p><p><span className="status-dot" /> Нет данных — состояние неизвестно.</p><div className="network-observations"><span>Домашняя сеть · {homeState.detail}</span><span>Выход · {exitState.detail}</span></div><p>GER и EST исключены из текущей схемы.</p></div></div>
    {selectedNode ? <Modal title={selectedNode.name} onClose={() => setSelected(null)}><div className="network-dialog"><p>Адрес подключения из реестра узлов</p><code>{selectedNode.host}</code><p>SSH</p><code>{selectedNode.ssh_user ? `${selectedNode.ssh_user}@` : ""}{selectedNode.host}:{selectedNode.ssh_port}</code><p>Связанные туннели</p>{links.filter(t => t.source_node_id === selected || t.target_node_id === selected).map(t => <div key={t.id}><strong>{t.name}</strong><code>{t.type} · {t.tunnel_cidr}</code></div>)}</div><div className="dialog-footer"><button className="secondary-button" onClick={() => setSelected(null)}>Закрыть</button></div></Modal> : null}
  </section>;
}
