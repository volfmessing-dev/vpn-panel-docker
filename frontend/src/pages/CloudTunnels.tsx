import { ArrowDownToLine, ArrowUpFromLine, Cable, Clock3, Globe2, Network, Router, UsersRound } from "lucide-react";
import type { CloudTunnelInterface, CloudTunnelPeer, CloudTunnelSnapshot, NodeRecord, VpnUserRecord } from "../types/api";

interface Props {
  snapshot: CloudTunnelSnapshot | null;
  nodes: NodeRecord[];
  users: VpnUserRecord[];
  now: number;
  hasData: boolean;
  stale: boolean;
  loading: boolean;
}

function formatBytes(value: number | null) {
  if (value === null) return "—";
  const units = ["Б", "КиБ", "МиБ", "ГиБ", "ТиБ"];
  const index = value <= 0 ? 0 : Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** index).toLocaleString("ru-RU", { maximumFractionDigits: index ? 1 : 0 })} ${units[index]}`;
}
function handshakeAge(value: number | null, now: number) {
  return value ? Math.max(0, Math.floor(now / 1000 - value)) : null;
}
function formatHandshake(value: number | null, now: number) {
  const age = handshakeAge(value, now);
  if (age === null) return "Нет handshake";
  if (age < 60) return `${age} сек. назад`;
  if (age < 3600) return `${Math.floor(age / 60)} мин. назад`;
  if (age < 86400) return `${Math.floor(age / 3600)} ч. назад`;
  return new Date(value! * 1000).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
function totalTraffic(peers: CloudTunnelPeer[], direction: "transfer_rx" | "transfer_tx") {
  const known = peers.map((peer) => peer[direction]).filter((value): value is number => value !== null);
  return known.length ? known.reduce((sum, value) => sum + value, 0) : null;
}
function isExit(item: CloudTunnelInterface) {
  return item.routes.some((route) => /^default\b/.test(route.trim()) && /\btable vpn_panel_exit\b/.test(route));
}

export function CloudTunnels({ snapshot, nodes, users, now, hasData, stale, loading }: Props) {
  const items = [...(snapshot?.interfaces ?? [])].sort((a, b) => Number(isExit(b)) - Number(isExit(a)) || a.name.localeCompare(b.name));
  const liveData = hasData && !stale && snapshot?.status === "up";
  const recent = (peer: CloudTunnelPeer) => {
    const age = handshakeAge(peer.latest_handshake, now);
    return age !== null && age < 180;
  };
  const peerCount = items.reduce((sum, item) => sum + item.peers.length, 0);
  const freshCount = items.reduce((sum, item) => sum + item.peers.filter(recent).length, 0);
  const nodeFor = (peer: CloudTunnelPeer) => nodes.find((node) => peer.endpoint?.startsWith(`${node.host}:`));
  const peerName = (peer: CloudTunnelPeer, index: number) => users.find((user) => user.public_key === peer.public_key)?.name || nodeFor(peer)?.name || `Peer ${index + 1}`;

  return (
    <section className="tunnels-page">
      <div className="users-intro">
        <div><h3>Соединения облачного шлюза</h3><p>{snapshot ? `${snapshot.node_name} · ${snapshot.host}` : "WireGuard и AmneziaWG"}</p></div>
        <span className="tunnel-readonly"><Network size={16} />Состояние подключений</span>
      </div>
      <div className="users-summary" aria-label="Сводка туннелей">
        <span><Cable size={17} /><strong>{liveData ? items.length : "—"}</strong> интерфейсов</span>
        <span><span className="status-dot" /><strong>{liveData ? items.filter((item) => item.flags.includes("LOWER_UP")).length : "—"}</strong> поднято</span>
        <span><UsersRound size={16} /><strong>{liveData ? `${freshCount}/${peerCount}` : "—"}</strong> peers со свежим handshake</span>
      </div>
      {snapshot?.status === "down" ? <div className="alert" role="alert"><strong>Не удалось получить состояние шлюза.</strong><p>Это ошибка проверки; состояние туннелей неизвестно.</p>{snapshot.error ? <details><summary>Подробнее</summary>{snapshot.error}</details> : null}</div> : null}
      <div className="tunnel-cards">
        {items.map((item) => {
          const exit = isExit(item);
          const home = item.name === "wg-ru-cloud";
          const exitNode = item.peers.map(nodeFor).find((node) => node?.role === "amnezia_exit");
          const title = exitNode?.name || (home ? "Домашняя сеть и пользователи" : item.display_name);
          const latest = Math.max(0, ...item.peers.map((peer) => peer.latest_handshake ?? 0)) || null;
          const freshPeers = item.peers.filter(recent).length;
          const up = item.flags.includes("LOWER_UP");
          const Icon = exit ? Globe2 : home ? Router : Cable;
          return (
            <article key={item.name} className="panel tunnel-card" aria-label={`Туннель ${item.name}`}>
              <div className="tunnel-card-header">
                <div className="tunnel-identity"><span className={`tunnel-icon ${exit ? "exit" : ""}`}><Icon size={24} /></span><div><span className="section-kicker">{exit ? "ВЫХОД ОБХОДА" : home ? "ПОДКЛЮЧЕНИЯ К ШЛЮЗУ" : "ОБЛАЧНЫЙ ТУННЕЛЬ"}</span><h3>{title}</h3><span className="tunnel-subtitle"><code>{item.name}</code> · {item.kind === "amneziawg" ? "AmneziaWG" : item.kind === "wireguard" ? "WireGuard" : "Тип не определён"}</span></div></div>
                <span className={`status-pill ${!liveData ? "neutral" : up ? "up" : "warning"}`}><span className="status-dot" />{!liveData ? "Нет свежих данных" : up ? "Интерфейс поднят" : "Интерфейс выключен"}</span>
              </div>
              <p className="tunnel-purpose">{exit ? "Выбранный выход для трафика из таблицы vpn_panel_exit." : home ? "Соединение домашней сети и устройств WireGuard с RU_Cloud." : "Дополнительный интерфейс шлюза. Назначение определяется правилами маршрутизации."}</p>
              <div className="tunnel-metrics">
                <div><span><Clock3 size={15} />Последний handshake</span><strong>{formatHandshake(latest, now)}</strong><small className={liveData && up && !freshPeers ? "handshake-warning" : ""}>{!liveData ? "Давность по последнему снимку" : freshPeers ? `${freshPeers} из ${item.peers.length} peers · менее 3 мин.` : "Нет peers со свежим handshake"}</small></div>
                <div><span><ArrowDownToLine size={15} />Получено шлюзом</span><strong>{formatBytes(totalTraffic(item.peers, "transfer_rx"))}</strong><small>От удалённой стороны</small></div>
                <div><span><ArrowUpFromLine size={15} />Отправлено шлюзом</span><strong>{formatBytes(totalTraffic(item.peers, "transfer_tx"))}</strong><small>К удалённой стороне</small></div>
              </div>
              <details className="tunnel-details">
                <summary>Peers и технические параметры <span>{item.peers.length} peers</span></summary>
                <div className="tunnel-details-body">
                  <div className="facts-grid">
                    <div className="fact"><span>Адреса интерфейса</span><code>{item.addresses.join(", ") || "—"}</code></div>
                    <div className="fact"><span>UDP-порт</span><code>{item.listen_port ?? "—"}</code></div>
                    <div className="fact"><span>MTU</span><code>{item.mtu ?? "—"}</code></div>
                    <div className="fact"><span>Метка маршрутизации</span><code>{item.fwmark ?? "—"}</code></div>
                    <div className="fact"><span>Состояние ядра</span><code>{item.operstate ?? "—"}</code></div>
                    <div className="facts-wide"><span>Публичный ключ интерфейса</span><code className="tunnel-key">{item.public_key || "—"}</code></div>
                  </div>
                  <div className="tunnel-peers">
                    {item.peers.map((peer, index) => <div className="tunnel-peer" key={peer.public_key}>
                      <div className="tunnel-peer-header"><strong>{peerName(peer, index)}</strong><span className={`status-pill ${liveData && up && recent(peer) ? "up" : "neutral"}`}>{!liveData ? "Нет свежих данных" : !up ? "Интерфейс выключен" : recent(peer) ? "Свежий handshake" : "Нет свежего handshake"}</span></div>
                      <div className="tunnel-peer-info"><span>Endpoint <code>{peer.endpoint || "Не определён"}</code></span><span>Разрешённые IP <code>{peer.allowed_ips.join(", ") || "—"}</code></span><span>Handshake <strong>{formatHandshake(peer.latest_handshake, now)}</strong></span><span>Трафик шлюза <strong>RX {formatBytes(peer.transfer_rx)} · TX {formatBytes(peer.transfer_tx)}</strong></span><span>Keepalive <code>{peer.persistent_keepalive ?? "—"}</code></span></div>
                      <details className="peer-key-details"><summary>Публичный ключ peer</summary><code className="tunnel-key">{peer.public_key}</code></details>
                    </div>)}
                    {!item.peers.length ? <p className="dialog-description">Peers на этом интерфейсе не обнаружены.</p> : null}
                  </div>
                  <details className="tunnel-routes"><summary>Маршруты интерфейса <span>{item.routes.length}</span></summary><pre className="compact-code">{item.routes.join("\n") || "Маршруты не обнаружены"}</pre></details>
                </div>
              </details>
            </article>
          );
        })}
        {!items.length ? <div className="panel empty-state tunnels-empty"><Cable size={30} /><h4>{loading && !hasData ? "Получаем данные туннелей" : !liveData ? "Состояние туннелей неизвестно" : "Интерфейсы не обнаружены"}</h4><p>{!liveData ? "Используйте «Обновить», чтобы повторить проверку шлюза." : "WireGuard и AmneziaWG отсутствуют в полученном снимке."}</p></div> : null}
      </div>
      {snapshot?.status === "up" ? <details className="panel tunnel-policy"><summary><span><Network size={17} />Правила маршрутизации шлюза</span><span>{snapshot.rules.length} правил</span></summary><pre className="compact-code">{snapshot.rules.join("\n") || "Правила не получены"}</pre></details> : null}
      <p className="users-footnote tunnel-footnote">Поднятый интерфейс и свежий handshake показаны отдельно. Они не подтверждают доступность сайтов через туннель. Трафик — сумма доступных счётчиков peers с момента запуска интерфейса.</p>
    </section>
  );
}
