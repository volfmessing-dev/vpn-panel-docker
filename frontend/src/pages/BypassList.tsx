import { useAutoRefresh } from "../hooks/useAutoRefresh";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ArrowRight, Check, Globe2, ListFilter, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { Modal } from "../components/Modal";
import { getVpnBypassStatus, refreshVpnBypass, updateVpnBypassDomains } from "../api/client";
import type { VpnBypassStatus, VpnUserApplyResult } from "../types/api";

const domainPattern = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const signature = (domains: string[]) => [...domains].sort().join("\n");
const normalizeDomain = (value: string) => value.trim().toLowerCase().replace(/\.+$/, "");

export function BypassList({ now, onNavigate, autoEnabled }: { now: number; autoEnabled: boolean; onNavigate: () => void }) {
  const [bypass, setBypass] = useState<VpnBypassStatus | null>(null);
  const baseline = useRef<VpnBypassStatus | null>(null);
  const [domains, setDomains] = useState<string[]>([]);
  const [newDomain, setNewDomain] = useState("");
  const [query, setQuery] = useState("");
  const [domainError, setDomainError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<VpnUserApplyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [confirmAction, setConfirmAction] = useState<"save" | "refresh" | null>(null);

  async function loadSnapshot() {
    try {
      const next = await getVpnBypassStatus();
      const previous = baseline.current;
      setDomains((current) => previous && signature(current) !== signature(previous.domains) ? current : next.domains);
      baseline.current = next; setBypass(next); setUpdatedAt(Date.now()); setLoadError(null);
    } catch (err) { setLoadError(err instanceof Error ? err.message : "Не удалось получить список"); }
  }
  async function refresh() {
    if (lock.current) return;
    lock.current = true; setBusy(true);
    try { await loadSnapshot(); }
    finally { lock.current = false; setBusy(false); }
  }
  useEffect(() => { void refresh(); }, []);
  useAutoRefresh(refresh, autoEnabled, "bypass-list");

  const added = domains.filter((domain) => !bypass?.domains.includes(domain));
  const removed = bypass?.domains.filter((domain) => !domains.includes(domain)) ?? [];
  const dirty = Boolean(bypass) && (added.length > 0 || removed.length > 0);
  const age = updatedAt ? Math.max(0, Math.floor((now - updatedAt) / 1000)) : null;
  const stale = Boolean(loadError) || (age !== null && age >= 180);
  const available = bypass?.status === "up" && !stale;
  const visibleDomains = [...domains].sort().filter((domain) => domain.includes(query.trim().toLowerCase()));
  const freshness = age === null ? "Список ещё не получен" : age < 10 ? "Только что обновлено" : age < 60 ? `Обновлено ${age} сек. назад` : `Обновлено ${Math.floor(age / 60)} мин. назад`;

  function addDomain(event: FormEvent) {
    event.preventDefault();
    if (busy || !bypass) return;
    const domain = normalizeDomain(newDomain);
    if (!domainPattern.test(domain)) { setDomainError("Введите домен без https://, пути и *. Например, example.com. Международные имена — в punycode."); return; }
    if (domains.includes(domain)) { setDomainError("Этот домен уже есть в списке."); return; }
    setDomains((current) => [...current, domain]); setNewDomain(""); setDomainError(null); setNotice(null);
  }
  async function executeAction() {
    if (lock.current || !available || !confirmAction || (confirmAction === "save" ? !dirty || !domains.length : dirty)) return;
    const action = confirmAction; setConfirmAction(null);
    lock.current = true; setBusy(true); setActionError(null); setNotice(null); setResult(null);
    try {
      if (action === "save") {
        // This API saves the file AND applies users/routing, rather than staging only.
        const saved = await updateVpnBypassDomains(domains);
        setDomains(saved.domains);
        if (baseline.current) {
          const next = { ...baseline.current, domains: saved.domains };
          baseline.current = next; setBypass(next);
        }
        setNotice("Список сохранён, обновление на шлюзе завершено.");
      } else {
        const response = await refreshVpnBypass(); setResult(response);
        if (response.status !== "applied") setActionError("Обновление на шлюзе не завершено. Проверьте подробности и состояние данных.");
      }
      await loadSnapshot();
    } catch (err) {
      setActionError(action === "save" ? "Не удалось завершить сохранение и обновление. Список мог сохраниться до ошибки применения. Проверьте загруженные данные перед повторной попыткой." : "Не удалось завершить обновление на шлюзе.");
      setResult({ status: "failed", message: err instanceof Error ? err.message : "Ошибка запроса", applied_users: 0 });
      // Read back the file: the API can persist it before returning an apply failure.
      await loadSnapshot();
    } finally { lock.current = false; setBusy(false); }
  }

  return (
    <section className="bypass-page">
      <div className="users-intro"><div><h3>Домены для обхода</h3><p>Сохранённый список и набор адресов на RU_Cloud.</p></div><div className="refresh-controls"><span className={`freshness ${stale ? "is-stale" : ""}`} role="status"><span className="status-dot" />{busy ? "Выполняем запрос…" : freshness}</span><button className="secondary-button refresh-button" onClick={refresh} disabled={busy}><RefreshCw size={16} className={busy ? "spin" : ""} />Обновить данные</button></div></div>
      <div className="dashboard-grid bypass-metrics"><div className="metric bypass-stat"><span className="metric-heading">Доменов в сохранённом списке<ListFilter size={18} /></span><strong>{bypass ? bypass.domains.length : "—"}</strong><span className="metric-detail">Изменения ниже остаются черновиком</span></div><div className="metric bypass-stat"><span className="metric-heading">Адресов в наборе<Globe2 size={18} /></span><strong>{bypass?.status === "up" ? bypass.ips.length.toLocaleString("ru-RU") : "—"}</strong><span className="metric-detail">IP доменов и статические диапазоны</span></div><div className="metric bypass-stat"><span className="metric-heading">Состояние данных</span><strong className="bypass-state">{!bypass || stale ? "Нет свежих данных" : bypass.status !== "up" ? "Проверка не удалась" : bypass.ips.length ? "Адреса доступны" : "Набор пуст"}</strong><span className="metric-detail">Результат последнего чтения шлюза</span></div></div>
      {loadError ? <div className="alert" role="alert"><strong>Не удалось обновить данные.</strong> {bypass ? "Показаны последние доступные данные; черновик сохранён." : "Повторите запрос."}<details><summary>Подробнее</summary>{loadError}</details></div> : bypass?.status === "down" ? <div className="alert" role="alert"><strong>Проверка шлюза не удалась.</strong> Состояние набора адресов неизвестно.{bypass.error ? <details><summary>Подробнее</summary>{bypass.error}</details> : null}</div> : stale ? <div className="stale-notice">Данные старше трёх минут. Обновите снимок перед выполнением изменений.</div> : null}
      {actionError ? <div className="alert" role="alert">{actionError}{result ? <details><summary>Подробнее</summary>{result.message}</details> : null}</div> : null}
      {notice ? <div className="user-notice" role="status"><Check size={17} /><span>{notice}</span></div> : result?.status === "applied" ? <div className="user-notice" role="status"><Check size={17} /><div><strong>Обновление на шлюзе завершено.</strong><details><summary>Подробнее</summary>{result.message}</details></div></div> : null}
      <div className="panel bypass-domains-panel"><div className="bypass-list-header"><div><span className="section-kicker">РЕДАКТОР СПИСКА</span><h3>Домены</h3></div><span className={`status-pill ${dirty ? "warning" : "neutral"}`}>{!bypass ? "Нет данных" : dirty ? `Черновик: +${added.length} / −${removed.length}` : "Сохранённый список"}</span></div>
        <form className="bypass-add" onSubmit={addDomain}><label>Добавить домен<input value={newDomain} onChange={(event) => { setNewDomain(event.target.value); setDomainError(null); }} aria-invalid={Boolean(domainError)} aria-describedby={domainError ? "bypass-domain-error" : undefined} placeholder="example.com" autoComplete="off" autoCapitalize="none" spellCheck={false} disabled={busy || !bypass} /></label><button type="submit" className="secondary-button inline-button" disabled={busy || !bypass || !newDomain.trim()}><Plus size={16} />Добавить в черновик</button></form>
        {domainError ? <p id="bypass-domain-error" className="bypass-field-error" role="alert">{domainError}</p> : null}
        <div className="bypass-search-row"><label className="user-search"><Search size={17} /><input aria-label="Поиск домена" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по списку" /></label><span>Показано {visibleDomains.length} из {domains.length}</span></div>
        <div className="bypass-domain-list">{visibleDomains.map((domain) => <div className="bypass-domain-row" key={domain}><Globe2 size={15} /><code>{domain}</code>{added.includes(domain) ? <span className="status-pill up">Добавлен</span> : null}<button className="icon-button bypass-remove" aria-label={`Убрать ${domain} из черновика`} title={domains.length === 1 ? "Список не может быть пустым" : "Убрать из черновика"} disabled={busy || domains.length <= 1} onClick={() => { setDomains((current) => current.filter((item) => item !== domain)); setNotice(null); }}><Trash2 size={15} /></button></div>)}{!visibleDomains.length ? <div className="empty-state users-empty"><ListFilter size={28} /><h4>{!bypass ? "Список ещё не получен" : "Домены не найдены"}</h4><p>{!bypass ? "Обновите данные, чтобы начать редактирование." : "Попробуйте другой поисковый запрос."}</p>{query ? <button className="text-button" onClick={() => setQuery("")}>Сбросить поиск</button> : null}</div> : null}</div>
        <div className="bypass-edit-footer"><p>{dirty ? `Добавлено: ${added.length} · удалено: ${removed.length}. Изменения ещё не отправлены.` : "Добавление и удаление здесь меняют только черновик."}</p><div className="button-row"><button className="secondary-button" disabled={busy || !dirty} onClick={() => { setDomains(bypass?.domains ?? []); setDomainError(null); }}>Сбросить черновик</button><button className="primary-button" disabled={busy || !dirty || !domains.length || !available} onClick={() => setConfirmAction("save")}>Сохранить и обновить</button></div></div>
      </div>
      <div className="panel bypass-route-note"><div><strong>Куда направляется трафик</strong><p>Выход для совпадений и остальных подключений задаётся правилами трафика.</p></div><button className="text-button inline-button" onClick={onNavigate}>Открыть правила<ArrowRight size={16} /></button></div>
      {bypass ? <details className="panel bypass-technical"><summary>Адреса и технические подробности</summary><div className="bypass-technical-body"><details><summary>Набор IP-адресов <span>{bypass.status === "up" ? bypass.ips.length : "—"}</span></summary><pre className="compact-code">{bypass.status !== "up" ? "Адреса недоступны" : bypass.ips.join("\n") || "Набор пуст"}</pre></details><details><summary>Правила маршрутизации</summary><pre className="compact-code">{bypass.rules.join("\n") || "Правила не получены"}</pre></details><details><summary>Маркировка трафика</summary><pre className="compact-code">{bypass.mangle.join("\n") || "Данные не получены"}</pre></details></div></details> : null}
      <div className="panel users-apply"><div><strong>Обновление на шлюзе</strong><p>Обновляет набор адресов и применяет сохранённые настройки пользователей и маршрутизации. Черновик доменов в эту операцию не входит.</p></div><button className="secondary-button inline-button" disabled={busy || !bypass || dirty || !available} onClick={() => setConfirmAction("refresh")}><RefreshCw size={16} />Обновить на шлюзе</button></div>
      {confirmAction ? <Modal title={confirmAction === "save" ? "Сохранить список и обновить шлюз?" : "Обновить настройки на шлюзе?"} onClose={() => setConfirmAction(null)}><p className="dialog-description">Будут обновлены адреса обхода и применены сохранённые настройки пользователей и маршрутизации на RU_Cloud.</p>{confirmAction === "save" ? <div className="bypass-review"><strong>Итоговый список: {domains.length} доменов</strong><div><span>Добавить · {added.length}</span><ul>{added.map((domain) => <li key={domain}>{domain}</li>)}</ul>{!added.length ? <p>Добавлений нет</p> : null}</div><div><span>Удалить · {removed.length}</span><ul>{removed.map((domain) => <li key={domain}>{domain}</li>)}</ul>{!removed.length ? <p>Удалений нет</p> : null}</div></div> : <p className="dialog-description">Будет использован сохранённый список: {bypass?.domains.length} доменов.</p>}{!available ? <div className="stale-notice">Закройте окно и получите свежие данные шлюза.</div> : null}<div className="dialog-footer"><button className="secondary-button" onClick={() => setConfirmAction(null)}>Отмена</button><button className="primary-button" disabled={busy || !available} onClick={executeAction}>{confirmAction === "save" ? "Сохранить и обновить" : "Обновить на шлюзе"}</button></div></Modal> : null}
    </section>
  );
}
