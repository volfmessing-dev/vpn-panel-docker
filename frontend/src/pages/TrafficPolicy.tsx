import { useAutoRefresh } from "../hooks/useAutoRefresh";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, ChevronDown, Clock3, FileCode2, Globe2, GitBranch, RefreshCw, Router, UserRound } from "lucide-react";
import { Modal } from "../components/Modal";
import { applyRoutingPolicies, getRoutingPolicies, getRoutingPolicyPreview, updateRoutingPolicy } from "../api/client";
import type { NodeRecord, RoutingPolicyApplyResult, RoutingPolicyPreview, RoutingPolicyRecord, RoutingPolicySnapshot, RoutingPolicySource, RoutingPolicyTarget } from "../types/api";

const labels: Record<RoutingPolicySource, string> = {
  wg_users_bypass: "Обход для пользователей",
  wg_users_default: "Остальной трафик пользователей",
  wg_mikrotik: "Обход домашней сети"
};
const descriptions: Record<RoutingPolicySource, string> = {
  wg_users_bypass: "Домены и IP из списка обхода на RU_Cloud",
  wg_users_default: "Трафик WireGuard, который не попал в список обхода",
  wg_mikrotik: "Трафик, отмеченный для обхода на MikroTik"
};
type ActionRecord = { fingerprint: string; status: "pending" | "applied"; at: number };
type ActionRecords = Partial<Record<RoutingPolicySource, ActionRecord>>;
const storageKey = "bypass-manager:policy-actions:v1";
const sources = Object.keys(labels) as RoutingPolicySource[];

function fingerprint(policy: RoutingPolicyRecord) {
  return JSON.stringify([policy.target, policy.target === "tunnel" ? policy.target_tunnel_id : null, policy.target === "direct" ? policy.direct_interface?.trim() : null, policy.enabled]);
}
function readActions(): ActionRecords {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) || "{}");
    const result: ActionRecords = {};
    for (const source of sources) {
      const item = parsed?.[source];
      if (typeof item?.fingerprint === "string" && (item.status === "pending" || item.status === "applied") && Number.isFinite(item.at)) result[source] = item;
    }
    return result;
  } catch { return {}; }
}
function timestamp(value: string | number) {
  return new Date(value).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function TrafficPolicy({ nodes, now, autoEnabled }: { nodes: NodeRecord[]; now: number; autoEnabled: boolean }) {
  const [snapshot, setSnapshot] = useState<RoutingPolicySnapshot | null>(null);
  const snapshotRef = useRef<RoutingPolicySnapshot | null>(null);
  const [previews, setPreviews] = useState<RoutingPolicyPreview[]>([]);
  const [previewFresh, setPreviewFresh] = useState(false);
  const [drafts, setDrafts] = useState<Partial<Record<RoutingPolicySource, RoutingPolicyRecord>>>({});
  const [actions, setActions] = useState<ActionRecords>(readActions);
  const [applyResult, setApplyResult] = useState<RoutingPolicyApplyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  useEffect(() => { try { localStorage.setItem(storageKey, JSON.stringify(actions)); } catch { /* Keep action tracking in memory if storage is unavailable. */ } }, [actions]);

  async function loadSnapshot() {
    try {
      const [data, previewData] = await Promise.all([getRoutingPolicies(), getRoutingPolicyPreview()]);
      const previous = snapshotRef.current;
      // Header refresh must not erase a draft the user is editing.
      setDrafts((current) => Object.fromEntries(data.policies.map((policy) => {
        const before = previous?.policies.find((item) => item.source === policy.source);
        const draft = current[policy.source];
        return [policy.source, before && draft && fingerprint(draft) !== fingerprint(before) ? draft : policy];
      })));
      snapshotRef.current = data; setSnapshot(data); setPreviews(previewData);
      setActions((current) => Object.fromEntries(data.policies.flatMap((policy) => {
        const action = current[policy.source];
        return action && action.fingerprint === fingerprint(policy) ? [[policy.source, action]] : [];
      })));
      setUpdatedAt(Date.now()); setPreviewFresh(true); setError(null);
    } catch (err) {
      setPreviewFresh(false);
      setError(err instanceof Error ? err.message : "Не удалось получить правила");
    }
  }
  async function refresh() {
    if (lock.current) return;
    lock.current = true; setBusy(true);
    try { await loadSnapshot(); }
    finally { lock.current = false; setBusy(false); }
  }
  useEffect(() => { void refresh(); }, []);
  useAutoRefresh(refresh, autoEnabled, "traffic-policy");

  const policies = snapshot?.policies ?? [];
  const retiredNodes = new Set(nodes.filter((node) => /^(GER|EST)_Amnezia$/i.test(node.name)).map((node) => node.id));
  const availableTunnels = snapshot?.available_tunnels.filter((tunnel) => !retiredNodes.has(tunnel.target_node_id) && !/\b(ger|est|germany|estonia)\b/i.test(tunnel.name.replace(/[-_]/g, " "))) ?? [];
  const destinationName = (policy: RoutingPolicyRecord) => {
    if (policy.target === "direct") return "Интернет через RU_Cloud";
    const tunnel = snapshot?.available_tunnels.find((item) => item.id === policy.target_tunnel_id);
    return nodes.find((node) => node.id === tunnel?.target_node_id)?.name || tunnel?.name || "Туннель не выбран";
  };
  const dirty = (policy: RoutingPolicyRecord) => Boolean(drafts[policy.source] && fingerprint(drafts[policy.source]!) !== fingerprint(policy));
  const pending = (policy: RoutingPolicyRecord) => actions[policy.source]?.status === "pending" && actions[policy.source]?.fingerprint === fingerprint(policy);
  const draftCount = policies.filter(dirty).length;
  const pendingCount = policies.filter(pending).length;
  const warningCount = previewFresh ? previews.reduce((sum, preview) => sum + preview.warnings.length, 0) : 0;
  const age = updatedAt ? Math.max(0, Math.floor((now - updatedAt) / 1000)) : null;
  const stale = Boolean(error) || (age !== null && age >= 180);
  const freshness = age === null ? "Правила ещё не получены" : age < 10 ? "Только что обновлено" : age < 60 ? `Обновлено ${age} сек. назад` : `Обновлено ${Math.floor(age / 60)} мин. назад`;

  function updateDraft(source: RoutingPolicySource, patch: Partial<RoutingPolicyRecord>) {
    setDrafts((current) => {
      const policy = current[source];
      return policy ? { ...current, [source]: { ...policy, ...patch } } : current;
    });
  }
  async function save(policy: RoutingPolicyRecord) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(null); setNotice(null);
    try {
      const saved = await updateRoutingPolicy(policy.source, {
        target: policy.target,
        target_tunnel_id: policy.target === "tunnel" ? policy.target_tunnel_id : null,
        direct_interface: policy.target === "direct" ? policy.direct_interface?.trim() || null : null,
        enabled: policy.enabled
      });
      const data = snapshotRef.current;
      if (data) {
        const next = { ...data, policies: data.policies.map((item) => item.source === saved.source ? saved : item) };
        snapshotRef.current = next; setSnapshot(next);
      }
      setDrafts((current) => ({ ...current, [saved.source]: saved }));
      setActions((current) => ({ ...current, [saved.source]: { fingerprint: fingerprint(saved), status: "pending", at: Date.now() } }));
      setApplyResult(null); setPreviewFresh(false);
      setNotice(`«${labels[policy.source]}» сохранено в панели. Маршруты на шлюзе ещё не изменены.`);
      await loadSnapshot();
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось сохранить правило"); }
    finally { lock.current = false; setBusy(false); }
  }
  async function applyPolicies() {
    if (lock.current || draftCount || !previewFresh || stale || warningCount) return;
    setConfirmApply(false);
    lock.current = true; setBusy(true); setError(null); setNotice(null);
    try {
      const result = await applyRoutingPolicies(); setApplyResult(result);
      if (result.status === "applied") {
        setActions(Object.fromEntries(policies.map((policy) => [policy.source, { fingerprint: fingerprint(policy), status: "applied", at: Date.now() }])));
      }
      await loadSnapshot();
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось применить правила"); }
    finally { lock.current = false; setBusy(false); }
  }

  return (
    <section className="policies-page">
      <div className="users-intro"><div><h3>Куда направляется трафик</h3><p>Сохранённые направления на RU_Cloud. Применение выполняется отдельно.</p></div><div className="refresh-controls"><span className={`freshness ${stale ? "is-stale" : ""}`} role="status"><span className="status-dot" />{busy ? "Выполняем запрос…" : freshness}</span><button className="secondary-button refresh-button" onClick={refresh} disabled={busy}><RefreshCw size={16} className={busy ? "spin" : ""} />Обновить</button></div></div>
      <div className="users-summary"><span><GitBranch size={17} /><strong>{snapshot ? policies.length : "—"}</strong> источника трафика</span><span><strong>{snapshot ? policies.filter((policy) => policy.enabled && policy.target === "tunnel").length : "—"}</strong> через туннель</span><span><strong>{snapshot ? policies.filter((policy) => policy.enabled && policy.target === "direct").length : "—"}</strong> напрямую</span>{draftCount ? <span className="policy-pending"><strong>{draftCount}</strong> черновиков</span> : null}{pendingCount ? <span className="policy-pending"><strong>{pendingCount}</strong> ожидают применения</span> : null}</div>
      {error ? <div className="alert" role="alert"><strong>Не удалось выполнить запрос.</strong> {snapshot ? "Показана последняя загруженная конфигурация." : "Повторите обновление."}<details><summary>Подробнее</summary>{error}</details></div> : stale ? <div className="stale-notice">Снимок правил старше трёх минут. Обновите его перед применением.</div> : null}
      {notice ? <div className="user-notice" role="status"><Check size={17} /><span>{notice}</span></div> : null}
      {applyResult ? <div className={applyResult.status === "applied" ? "user-notice" : "alert"} role="status"><div><strong>{applyResult.status === "applied" ? "Правила успешно применены." : "Не удалось применить правила."}</strong>{applyResult.status === "applied" ? <p>Пользователей: {applyResult.applied_users} · туннелей обновлено: {applyResult.reapplied_tunnel_ids.length}</p> : null}<details><summary>Подробнее</summary>{applyResult.message}{applyResult.warnings.length ? <p>{applyResult.warnings.join("; ")}</p> : null}</details></div></div> : null}
      <div className="policy-cards">
        {policies.map((policy) => {
          const draft = drafts[policy.source] ?? policy;
          const hasDraft = dirty(policy);
          const action = actions[policy.source]?.fingerprint === fingerprint(policy) ? actions[policy.source] : undefined;
          const preview = previews.find((item) => item.source === policy.source);
          const canUseDirect = policy.source === "wg_users_default";
          const valid = draft.target === "tunnel" ? availableTunnels.some((tunnel) => tunnel.id === draft.target_tunnel_id && tunnel.enabled) : canUseDirect && Boolean(draft.direct_interface?.trim());
          const Icon = policy.source === "wg_mikrotik" ? Router : UserRound;
          return <article key={policy.source} className={`panel policy-card ${hasDraft || pending(policy) ? "has-changes" : ""}`} aria-label={labels[policy.source]}>
            <div className="policy-card-top"><span className="section-kicker">СОХРАНЁННОЕ ПРАВИЛО</span><span className={`status-pill ${hasDraft || pending(policy) ? "warning" : "neutral"}`}>{hasDraft ? "Несохранённый черновик" : pending(policy) ? "Ожидает применения" : action?.status === "applied" ? "Применялось из этого браузера" : "Сохранено в панели"}</span></div>
            <div className="policy-flow"><div className="policy-source"><span className="tunnel-icon"><Icon size={23} /></span><div><h3>{labels[policy.source]}</h3><p>{descriptions[policy.source]}</p></div></div><div className="policy-arrow"><ArrowRight size={24} /></div><div className="policy-destination"><span className={`tunnel-icon ${policy.target === "tunnel" ? "exit" : ""}`}><Globe2 size={23} /></span><div><span>{policy.enabled ? policy.target === "tunnel" ? "Туннель AmneziaWG" : "Прямой выход" : "Правило отключено в панели"}</span><strong>{destinationName(policy)}</strong><code>{policy.resolved_interface || "Интерфейс не определён"}</code></div></div></div>
            <div className="policy-history"><Clock3 size={13} /><span>{action ? `${action.status === "pending" ? "Сохранено" : "Успешное применение"} ${timestamp(action.at)} · этот браузер` : policy.applied_at ? `Последняя зарегистрированная дата применения: ${timestamp(policy.applied_at)}` : "Дата применения не зарегистрирована"}</span></div>
            {previewFresh && preview?.warnings.length ? <div className="policy-warning">{preview.warnings.join("; ")}</div> : null}
            <details className="policy-editor"><summary><span>Изменить направление</span><ChevronDown size={16} /></summary><div className="policy-editor-body"><div className="policy-edit-fields"><label>Тип выхода<select value={draft.target} disabled={busy} onChange={(event) => updateDraft(policy.source, { target: event.target.value as RoutingPolicyTarget })}><option value="tunnel">Туннель AmneziaWG</option>{canUseDirect ? <option value="direct">Прямой интерфейс RU_Cloud</option> : null}</select></label>{draft.target === "tunnel" ? <label>Выходной туннель<select value={draft.target_tunnel_id ?? ""} disabled={busy} onChange={(event) => updateDraft(policy.source, { target_tunnel_id: Number(event.target.value) || null })}><option value="">Выберите туннель</option>{availableTunnels.map((tunnel) => <option key={tunnel.id} value={tunnel.id} disabled={!tunnel.enabled}>{nodes.find((node) => node.id === tunnel.target_node_id)?.name || tunnel.name} · {tunnel.tunnel_cidr}</option>)}</select></label> : <label>Интерфейс<input value={draft.direct_interface ?? ""} maxLength={32} disabled={busy} onChange={(event) => updateDraft(policy.source, { direct_interface: event.target.value })} placeholder="enp3s0" /></label>}</div><label className="checkbox-label"><input type="checkbox" checked={draft.enabled} disabled={busy} onChange={(event) => updateDraft(policy.source, { enabled: event.target.checked })} />Включить правило в панели</label>{hasDraft ? <div className="policy-draft-preview"><span>Черновик</span><strong>{draft.enabled ? destinationName(draft) : "Правило будет отключено"}</strong></div> : null}<div className="policy-edit-footer"><p>Сохранение обновляет правило в панели. Для изменения маршрутов используйте «Применить правила».</p><div className="button-row"><button className="secondary-button" disabled={busy || !hasDraft} onClick={() => setDrafts((current) => ({ ...current, [policy.source]: policy }))}>Сбросить черновик</button><button className="primary-button" disabled={busy || !hasDraft || !valid} onClick={() => save(draft)}>Сохранить правило</button></div></div></div></details>
          </article>;
        })}
        {!policies.length ? <div className="panel empty-state tunnels-empty"><GitBranch size={30} /><h4>{busy ? "Получаем правила" : "Правила не получены"}</h4><p>Обновите данные, чтобы увидеть направления трафика.</p></div> : null}
      </div>
      {snapshot ? <details className="panel policy-preview"><summary><span><FileCode2 size={17} />Предпросмотр сохранённых правил</span><ChevronDown size={17} /></summary>{previewFresh ? <div className="policy-preview-list">{previews.map((preview) => <div className="preview-item" key={preview.source}><strong>{labels[preview.source]}</strong><span>Интерфейс: {preview.resolved_interface || "не определён"}</span>{preview.warnings.length ? <span className="policy-warning">{preview.warnings.join("; ")}</span> : null}<pre className="compact-code">{preview.commands.join("\n") || "Команды отсутствуют"}</pre></div>)}</div> : <p className="dialog-description">Предпросмотр недоступен. Обновите данные перед применением.</p>}</details> : null}
      <div className="panel users-apply policy-apply"><div><strong>{draftCount ? "Сначала сохраните или сбросьте черновики" : pendingCount ? `Ожидают применения: ${pendingCount}` : "Применение сохранённых правил"}</strong><p>{warningCount ? "В предпросмотре есть предупреждения. Исправьте правила перед применением." : "Применение обновляет маршрутизацию и подключения на RU_Cloud."}</p></div><button className="primary-button inline-button" onClick={() => setConfirmApply(true)} disabled={busy || !snapshot || !policies.length || draftCount > 0 || !previewFresh || stale || warningCount > 0}><Check size={17} />Применить правила</button></div>
      {confirmApply ? <Modal title="Применить сохранённые правила?" onClose={() => setConfirmApply(false)}><p className="dialog-description">Будут обновлены маршрутизация и подключения на RU_Cloud. Проверьте направления перед применением.</p><div className="policy-confirm-list">{policies.map((policy) => <div key={policy.source}><span>{labels[policy.source]}</span><strong>{policy.enabled ? destinationName(policy) : "Правило отключено"}</strong><code>{policy.resolved_interface || "—"}</code></div>)}</div>{stale ? <div className="stale-notice">Снимок устарел. Закройте окно и обновите правила.</div> : null}<div className="dialog-footer"><button className="secondary-button" onClick={() => setConfirmApply(false)}>Отмена</button><button className="primary-button" onClick={applyPolicies} disabled={busy || draftCount > 0 || !previewFresh || stale || warningCount > 0}>Применить на RU_Cloud</button></div></Modal> : null}
      <p className="users-footnote tunnel-footnote">Пометки о сохранении и применении относятся к действиям из этого браузера. Схема показывает конфигурацию панели; фактические маршруты шлюза доступны в разделе «Туннели».</p>
    </section>
  );
}
