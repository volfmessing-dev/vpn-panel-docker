import { useState } from "react";
import { Plus, Server, Router, Pencil, Trash2, Search, Activity, FileText } from "lucide-react";
import { nodeTunnelStatuses } from "../lib/nodeTunnelStatus";
import { Modal } from "../components/Modal";
import { createNode, deleteNode, collectSingleNodeFacts, checkSingleNode, updateNode } from "../api/client";
import type { CloudTunnelSnapshot, NodeFacts, NodeHealth, NodeRecord, NodeRole, NodeUplinkType, TunnelRecord } from "../types/api";

interface Props { nodes: NodeRecord[]; tunnels: TunnelRecord[]; now: number; hasData: boolean; stale: boolean; cloudTunnels: CloudTunnelSnapshot | null; onChanged: () => Promise<void>; }
const roles: Record<NodeRole, string> = { mikrotik: "Домашний маршрутизатор", ru_cloud: "Облачный шлюз", amnezia_exit: "Выходной сервер" };
const archived = (node: NodeRecord) => /^(GER|EST)(_|$)/i.test(node.name);
const blank = { name: "", role: "amnezia_exit" as NodeRole, host: "", ssh_user: "", ssh_port: 22 };

export function Nodes({ nodes, tunnels, now, hasData, stale, cloudTunnels, onChanged }: Props) {
  const [query, setQuery] = useState("");
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState<NodeRecord | null>(null);
  const [open, setOpen] = useState(false);
  const [removing, setRemoving] = useState<NodeRecord | null>(null);
  const [uplink, setUplink] = useState<NodeUplinkType>("none");
  const [health, setHealth] = useState<NodeHealth[]>([]);
  const [facts, setFacts] = useState<NodeFacts[]>([]);
  const [signatures, setSignatures] = useState<Record<number, string>>({});
  const [pending, setPending] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const legacy = nodes.filter(archived);
  const current = nodes.filter(node => !archived(node));
  const currentTunnels = tunnels.filter(t => !legacy.some(n => n.id === t.source_node_id || n.id === t.target_node_id));
  const visible = current.filter(node => `${node.name} ${node.host} ${roles[node.role]}`.toLowerCase().includes(query.toLowerCase().trim()));

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(null); setNotice(null);
    try { await action(); } catch (err) { setError(err instanceof Error ? err.message : "Не удалось выполнить действие"); }
    finally { setBusy(false); }
  }
  function edit(node: NodeRecord | null) {
    setEditing(node); setForm(node ? { ...node, ssh_user: node.ssh_user ?? "" } : blank); setUplink("none"); setError(null); setOpen(true);
  }
  async function save() {
    await run(async () => {
      const payload = { ...form, name: form.name.trim(), host: form.host.trim(), ssh_user: form.ssh_user.trim() || null };
      if (!payload.name || !payload.host || !Number.isInteger(payload.ssh_port) || payload.ssh_port < 1 || payload.ssh_port > 65535) throw new Error("Укажите имя, адрес и SSH-порт от 1 до 65535.");
      if (editing) { await updateNode(editing.id, payload); setNotice(`Узел ${payload.name} обновлён.`); }
      else {
        const result = await createNode({ ...payload, uplink_type: uplink });
        setNotice(result.apply_error ? `Узел создан. Применение туннеля не завершено: ${result.apply_error}` : result.apply_result?.status === "applied" ? "Узел создан, туннель применён на сервере." : result.created_tunnel ? "Узел и конфигурация туннеля созданы." : "Узел создан.");
      }
      setOpen(false); setHealth([]); setFacts([]); await onChanged();
    });
  }
  function signature(node: NodeRecord) {
    return JSON.stringify([node.name, node.host, node.role, node.ssh_user, node.ssh_port]);
  }
  async function check(node: NodeRecord, kind: "health" | "facts") {
    const key = signature(node);
    setPending(`${node.id}-${kind}`);
    await run(async () => {
      if (signatures[node.id] !== key) {
        setHealth(previous => previous.filter(item => item.node_id !== node.id));
        setFacts(previous => previous.filter(item => item.node_id !== node.id));
      }
      setSignatures(previous => ({ ...previous, [node.id]: key }));
      try {
        if (kind === "health") {
          const result = await checkSingleNode(node.id);
          setHealth(previous => [...previous.filter(item => item.node_id !== node.id), result]);
        } else {
          const result = await collectSingleNodeFacts(node.id);
          setFacts(previous => [...previous.filter(item => item.node_id !== node.id), result]);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "Не удалось получить ответ API";
        const checked_at = new Date().toISOString();
        if (kind === "health") setHealth(previous => [...previous.filter(item => item.node_id !== node.id), { node_id: node.id, name: node.name, status: "unknown", check: "api", message, latency_ms: null, checked_at }]);
        else setFacts(previous => [...previous.filter(item => item.node_id !== node.id), { node_id: node.id, name: node.name, status: "down", error: message, checked_at, hostname: null, os: null, kernel: null, public_ip: null, ip_forward: null, docker: null, wireguard: null, interfaces: [], routes: [] }]);
      }
    });
    setPending(null);
  }
  function checkedLabel(value: string | null | undefined) {
    return value ? new Date(value).toLocaleString("ru-RU") : "Нет времени проверки";
  }
  return <section className="users-page nodes-page">
    <div className="users-intro"><div><h3>Узлы сети</h3><p>Маршрутизатор, облачный шлюз и выходные серверы.</p></div><button className="primary-button" disabled={busy} onClick={() => edit(null)}><Plus size={18} /> Добавить узел</button></div>
    <div className="users-summary"><span><strong>{current.length}</strong> активных записей</span><span><strong>{currentTunnels.length}</strong> туннелей</span><span>{`Управление проверено ${current.filter(node => signatures[node.id] === signature(node) && health.some(item => item.node_id === node.id)).length} из ${current.length}` }</span></div>
    {error && !open ? <div className="alert" role="alert">{error}</div> : null}
    {notice ? <div className="user-notice" role="status">{notice}</div> : null}
    <div className="panel nodes-toolbar"><label className="user-search"><Search size={18} /><input aria-label="Поиск узлов" placeholder="Имя, адрес или роль" value={query} onChange={e => setQuery(e.target.value)} /></label><span className="nodes-hint">Активность туннеля и доступность управления показаны отдельно.</span></div>
    <div className="nodes-grid">{visible.map(node => {
      const status = signatures[node.id] === signature(node) ? health.find(h => h.node_id === node.id) : undefined;
      const old = !!status?.checked_at && now - Date.parse(status.checked_at) > 180000;
      const info = signatures[node.id] === signature(node) ? facts.find(f => f.node_id === node.id) : undefined;
      const links = currentTunnels.filter(t => t.source_node_id === node.id || t.target_node_id === node.id);
      return <article className="panel nodes-card" key={node.id}><div className="nodes-card-head"><span className="nodes-icon">{node.role === "mikrotik" ? <Router size={23} /> : <Server size={23} />}</span><div><h4>{node.name}</h4><p>{roles[node.role]}</p></div></div>
        <div className="nodes-address"><span>Адрес узла</span><code>{node.host}</code></div>
        <div className="nodes-links"><span>Туннели</span><strong>{links.length}</strong></div>
        <div className="nodes-statuses">
          <div className="nodes-tunnel-status" aria-label={`Туннель ${node.name}`}>
            {nodeTunnelStatuses(node, current, currentTunnels, cloudTunnels, now, hasData, stale).map(item => <div key={item.key}><div className="nodes-status-heading"><span>{item.title}</span><span className={`status-pill ${item.tone}`}>{item.label}</span></div><small>{item.detail}</small></div>)}
            {node.role === "ru_cloud" && !links.length ? <p>Связанных туннелей нет.</p> : null}
          </div>
          <div className="nodes-status-heading"><span>Управление · {node.role === "mikrotik" || !node.ssh_user ? "TCP" : "SSH"}</span><span className={`status-pill ${old ? "neutral" : status?.status === "up" ? "up" : status?.status === "down" ? "warning" : "neutral"}`}>{old ? "Проверка устарела" : status?.status === "up" ? status.check === "tcp" ? "TCP-порт доступен" : "SSH доступен" : status?.status === "down" ? status.check === "tcp" ? "TCP недоступен" : "SSH-проверка не пройдена" : status ? "Статус неизвестен" : "Не проверен"}</span></div>
        </div>
        <div className="nodes-check-result" aria-live="polite">{status ? <><span>Проверено: {checkedLabel(status.checked_at)}</span><p>{status.message}{status.latency_ms !== null ? ` · Длительность ${status.latency_ms} мс` : ""}</p></> : <p>Проверка из облачного шлюза ещё не запускалась.</p>}</div>
        <div className="nodes-check-actions"><button className="secondary-button" disabled={busy || !hasData} onClick={() => check(node, "health")}><Activity size={15} />{pending === `${node.id}-health` ? "Проверяем…" : "Проверить управление"}</button></div>
        <details className="nodes-details"><summary>Подключение и подробности</summary><dl><dt>SSH</dt><dd><code>{node.ssh_user ? `${node.ssh_user}@` : ""}{node.host}:{node.ssh_port}</code></dd></dl>{links.map(t => <p key={t.id}>{t.name} · {t.type} · {t.tunnel_cidr}</p>)}{status ? <p>{status.message}{status.latency_ms !== null ? ` · ${status.latency_ms} мс` : ""}</p> : null}<button className="secondary-button" disabled={busy || !hasData || node.role === "mikrotik"} onClick={() => check(node, "facts")}><FileText size={15} />{pending === `${node.id}-facts` ? "Загружаем…" : "Получить сведения"}</button>{node.role === "mikrotik" ? <p>Системные сведения RouterOS пока не поддерживаются.</p> : info ? <><p>Сведения получены: {checkedLabel(info.checked_at)}</p><FactsBlock facts={info} /></> : <p>Системные сведения ещё не загружены.</p>}</details>
        <footer><button className="text-button" disabled={busy} onClick={() => edit(node)}><Pencil size={15} /> Изменить</button><button className="icon-button danger" aria-label={`Удалить ${node.name}`} title={node.role === "ru_cloud" ? "Облачный шлюз защищён от удаления" : "Удалить узел"} disabled={busy || node.role === "ru_cloud"} onClick={() => setRemoving(node)}><Trash2 size={17} /></button></footer></article>;
    })}</div>
    <p className="nodes-hint">Активность туннеля основана на handshake конкретного peer за последние 3 минуты. Она не подтверждает доступность сайтов. Закрытый порт управления не означает, что туннель отключён.</p>
    {!visible.length ? <div className="panel empty-state">{current.length ? "Узлы по этому запросу не найдены." : "Узлов пока нет. Добавьте первое устройство."}</div> : null}
    {legacy.length ? <details className="panel nodes-archive"><summary>Архивные записи · {legacy.length}</summary><p>Сохранены в базе. Не входят в текущую сеть.</p>{legacy.map(node => <div key={node.id}><strong>{node.name}</strong><code>{node.host}</code><span className="status-pill neutral">Архив</span></div>)}</details> : null}
    {open ? <Modal title={editing ? "Изменить узел" : "Добавить узел"} busy={busy} onClose={() => setOpen(false)}><form className="user-form" onSubmit={e => { e.preventDefault(); void save(); }}><p className="dialog-description">Адрес и SSH-параметры используются для управления устройством.</p>{error ? <div className="alert" role="alert">{error}</div> : null}<label>Имя<input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label><label>Роль<select value={form.role} onChange={e => { setForm({ ...form, role: e.target.value as NodeRole }); setUplink("none"); }}>{Object.entries(roles).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Адрес<input required value={form.host} onChange={e => setForm({ ...form, host: e.target.value })} placeholder="IP-адрес или имя хоста" /></label><label>Пользователь SSH<input value={form.ssh_user} onChange={e => setForm({ ...form, ssh_user: e.target.value })} /></label><label>Порт SSH<input required type="number" min={1} max={65535} step={1} value={form.ssh_port} onChange={e => setForm({ ...form, ssh_port: Number(e.target.value) })} /></label>{!editing && form.role === "amnezia_exit" ? <label>Туннель к RU Cloud<select value={uplink} onChange={e => setUplink(e.target.value as NodeUplinkType)}><option value="none">Без туннеля</option><option value="wireguard">WireGuard</option><option value="amneziawg">AmneziaWG</option></select></label> : null}{uplink === "amneziawg" ? <div className="stale-notice">Создание узла также применит AmneziaWG-туннель на серверах.</div> : null}<div className="dialog-footer"><button type="button" className="secondary-button" disabled={busy} onClick={() => setOpen(false)}>Отмена</button><button className="primary-button" disabled={busy}>{busy ? "Сохранение…" : editing ? "Сохранить" : "Создать узел"}</button></div></form></Modal> : null}
    {removing ? <Modal title="Удалить узел?" busy={busy} onClose={() => setRemoving(null)}><p className="dialog-description">Будут удалены запись {removing.name} и связанные туннели из панели.</p>{error ? <div className="alert" role="alert">{error}</div> : null}<div className="dialog-footer"><button className="secondary-button" disabled={busy} onClick={() => setRemoving(null)}>Отмена</button><button className="primary-button danger" disabled={busy} onClick={() => run(async () => { await deleteNode(removing.id); setRemoving(null); setNotice("Узел удалён."); await onChanged(); })}>Удалить узел</button></div></Modal> : null}
  </section>;
}

function FactsBlock({ facts }: { facts: NodeFacts }) {
  if (facts.status !== "up") {
    return <div className="facts-error" role="alert">{facts.status === "unsupported" ? "Сведения для этого устройства не поддерживаются." : `Не удалось получить сведения: ${facts.error ?? facts.status}`}</div>;
  }

  return (
    <div className="facts-grid">
      <Fact label="Имя системы" value={facts.hostname} />
      <Fact label="OS" value={facts.os} />
      <Fact label="Kernel" value={facts.kernel} />
      <Fact label="Public IP" value={facts.public_ip} />
      <Fact label="IPv4 forward" value={facts.ip_forward} />
      <Fact label="Docker" value={facts.docker} />
      <Fact label="WG/AWG" value={facts.wireguard} />
      <div className="facts-wide">
        <span>Интерфейсы</span>
        <pre>{facts.interfaces.join("\n") || "Нет данных"}</pre>
      </div>
      <div className="facts-wide">
        <span>Маршруты</span>
        <pre>{facts.routes.join("\n") || "Нет данных"}</pre>
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="fact">
      <span>{label}</span>
      <code>{value || "Нет данных"}</code>
    </div>
  );
}
