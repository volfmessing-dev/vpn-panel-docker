import { useState } from "react";
import type { FormEvent } from "react";
import { ArrowDownToLine, ArrowUpFromLine, Check, Download, FileText, Pencil, Plus, QrCode, Search, Trash2, UserRound, UsersRound } from "lucide-react";
import { Modal } from "../components/Modal";
import { applyVpnUsers, createVpnUser, deleteVpnUser, getVpnUserConfig, updateVpnUser, vpnUserDownloadUrl, vpnUserQrUrl } from "../api/client";
import type { CloudTunnelPeer, CloudTunnelSnapshot, VpnUserApplyResult, VpnUserConfig, VpnUserRecord } from "../types/api";

interface Props {
  users: VpnUserRecord[];
  cloudTunnels: CloudTunnelSnapshot | null;
  now: number;
  hasData: boolean;
  stale: boolean;
  loading: boolean;
  onChanged: () => Promise<void>;
}
type Filter = "all" | "online" | "offline" | "disabled";
type Dialog = { kind: "form"; user: VpnUserRecord | null } | { kind: "qr"; user: VpnUserRecord } | { kind: "config"; user: VpnUserRecord; config: VpnUserConfig };

function formatBytes(value: number | null | undefined) {
  if (value == null) return "—";
  const units = ["Б", "КиБ", "МиБ", "ГиБ", "ТиБ"];
  const index = value <= 0 ? 0 : Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** index).toLocaleString("ru-RU", { maximumFractionDigits: index ? 1 : 0 })} ${units[index]}`;
}
function handshakeLabel(timestamp: number | null, now: number) {
  if (!timestamp) return "Нет handshake";
  const age = Math.max(0, Math.floor(now / 1000 - timestamp));
  if (age < 60) return `${age} сек. назад`;
  if (age < 3600) return `${Math.floor(age / 60)} мин. назад`;
  if (age < 86400) return `${Math.floor(age / 3600)} ч. назад`;
  return new Date(timestamp * 1000).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function Users({ users, cloudTunnels, now, hasData, stale, loading, onChanged }: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [applyResult, setApplyResult] = useState<VpnUserApplyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingChanges, setPendingChanges] = useState(false);
  const [qrError, setQrError] = useState(false);

  const interfaceData = cloudTunnels?.interfaces.find((item) => item.name === "wg-ru-cloud");
  const peers = new Map((interfaceData?.peers ?? []).map((peer) => [peer.public_key, peer]));
  const liveData = hasData && !stale && cloudTunnels?.status === "up" && Boolean(interfaceData);
  function peerFor(user: VpnUserRecord): CloudTunnelPeer | undefined { return peers.get(user.public_key); }
  function lastHandshake(user: VpnUserRecord) { return peerFor(user)?.latest_handshake ?? user.latest_handshake; }
  function statusFor(user: VpnUserRecord) {
    if (!user.enabled) return { label: "Отключён", tone: "neutral", id: "disabled" };
    if (!liveData) return { label: "Нет свежих данных", tone: "neutral", id: "unknown" };
    const handshake = lastHandshake(user);
    if (handshake && now / 1000 - handshake < 180) return { label: "Онлайн", tone: "up", id: "online" };
    return { label: "Нет подключения", tone: "neutral", id: "offline" };
  }
  const visibleUsers = users.filter((user) => {
    const matchesQuery = `${user.name} ${user.client_ip}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
    return matchesQuery && (filter === "all" || statusFor(user).id === filter);
  });
  const onlineCount = users.filter((user) => statusFor(user).id === "online").length;
  const locked = busy || loading;

  function openForm(user: VpnUserRecord | null = null) {
    setName(user?.name ?? ""); setEnabled(user?.enabled ?? true);
    setFormError(null); setError(null); setDialog({ kind: "form", user });
  }
  function openQr(user: VpnUserRecord) { setQrError(false); setDialog({ kind: "qr", user }); }

  async function saveUser(event: FormEvent) {
    event.preventDefault();
    if (dialog?.kind !== "form" || !name.trim() || locked) return;
    const editing = dialog.user;
    setBusy(true); setFormError(null);
    try {
      const saved = editing ? await updateVpnUser(editing.id, { name: name.trim(), enabled }) : await createVpnUser({ name: name.trim(), enabled });
      setPendingChanges(true); setApplyResult(null);
      setNotice(editing ? "Изменения сохранены. Примените список на шлюзе." : "Пользователь создан. Примените список на шлюзе, затем подключите устройство.");
      // Close the form before refreshing: a read failure must not invite a duplicate create.
      setDialog(null);
      await onChanged();
      if (!editing) openQr(saved);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Не удалось сохранить пользователя");
    } finally { setBusy(false); }
  }
  async function removeUser(user: VpnUserRecord) {
    if (!window.confirm(`Удалить пользователя «${user.name}»? Его конфигурацию нельзя будет восстановить через панель. После удаления примените список на шлюзе.`)) return;
    setBusy(true); setError(null);
    try {
      await deleteVpnUser(user.id);
      setPendingChanges(true); setApplyResult(null);
      setNotice(`Пользователь «${user.name}» удалён. Примените список на шлюзе.`);
      await onChanged();
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось удалить пользователя"); }
    finally { setBusy(false); }
  }
  async function showConfig(user: VpnUserRecord) {
    setBusy(true); setError(null);
    try { setDialog({ kind: "config", user, config: await getVpnUserConfig(user.id) }); }
    catch (err) { setError(err instanceof Error ? err.message : "Не удалось загрузить конфигурацию"); }
    finally { setBusy(false); }
  }
  async function applyUsers() {
    setBusy(true); setError(null); setNotice(null);
    try {
      const result = await applyVpnUsers(); setApplyResult(result);
      if (result.status === "applied") setPendingChanges(false);
      await onChanged();
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось применить список"); }
    finally { setBusy(false); }
  }

  return (
    <section className="users-page">
      <div className="users-intro">
        <div><h3>Устройства и подключения</h3><p>Доступ WireGuard через облачный шлюз.</p></div>
        <button className="primary-button inline-button" onClick={() => openForm()} disabled={locked}><Plus size={17} />Добавить пользователя</button>
      </div>
      <div className="users-summary" aria-label="Сводка пользователей">
        <span><UsersRound size={17} /><strong>{hasData ? users.length : "—"}</strong> всего</span>
        <span><span className="status-dot" /><strong>{liveData ? onlineCount : "—"}</strong> онлайн</span>
        <span><strong>{hasData ? users.filter((user) => user.enabled).length : "—"}</strong> включено</span>
        <span><strong>{hasData ? users.filter((user) => !user.enabled).length : "—"}</strong> отключено</span>
      </div>
      {error ? <div className="alert" role="alert"><strong>Не удалось выполнить действие.</strong><details><summary>Подробнее</summary>{error}</details></div> : null}
      {notice ? <div className="user-notice" role="status"><Check size={17} /><span>{notice}</span></div> : null}
      {applyResult ? <div className={applyResult.status === "applied" ? "user-notice" : "alert"} role="status"><div><strong>{applyResult.status === "applied" ? `Список применён: ${applyResult.applied_users} пользователей.` : "Не удалось применить список."}</strong><details><summary>Подробнее</summary>{applyResult.message}</details></div></div> : null}
      <div className="panel users-list-panel">
        <div className="users-toolbar">
          <label className="user-search"><Search size={17} /><input aria-label="Поиск пользователя" placeholder="Поиск по имени или IP" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <select aria-label="Статус подключения" value={filter} onChange={(event) => setFilter(event.target.value as Filter)}><option value="all">Все пользователи</option><option value="online">Онлайн</option><option value="offline">Нет подключения</option><option value="disabled">Отключённые</option></select>
        </div>
        <div className="users-table-heading" aria-hidden="true"><span>Пользователь</span><span>Последний handshake</span><span>Трафик шлюза</span><span>Действия</span></div>
        <div className="user-cards">
          {visibleUsers.map((user) => {
            const status = statusFor(user);
            const peer = peerFor(user);
            return <article className="user-card" key={user.id} aria-label={`Пользователь ${user.name}`}>
              <div className="user-card-main">
                <div className="user-identity"><span className="user-avatar"><UserRound size={20} /></span><div><h4>{user.name}</h4><span className="user-ip">{user.client_ip}</span><span className={`status-pill ${status.tone}`}><span className="status-dot" />{status.label}</span></div></div>
                <div className="user-handshake"><span className="mobile-field-label">Последний handshake</span><strong title={lastHandshake(user) ? new Date(lastHandshake(user)! * 1000).toLocaleString("ru-RU") : undefined}>{handshakeLabel(lastHandshake(user), now)}</strong><span>{user.applied_at ? "Конфигурация применялась" : "Ещё не применён"}</span></div>
                <div className="user-traffic"><span className="mobile-field-label">Трафик шлюза</span><span><ArrowDownToLine size={13} /><strong>{formatBytes(peer?.transfer_rx)}</strong><small>от устройства</small></span><span><ArrowUpFromLine size={13} /><strong>{formatBytes(peer?.transfer_tx)}</strong><small>к устройству</small></span></div>
                <div className="user-actions"><button className="secondary-button inline-button" aria-label={`QR-код для ${user.name}`} onClick={() => openQr(user)} disabled={locked}><QrCode size={16} />QR-код</button><button className="icon-button" aria-label={`Редактировать ${user.name}`} title="Редактировать" onClick={() => openForm(user)} disabled={locked}><Pencil size={16} /></button></div>
              </div>
              <details className="user-details"><summary>Подробности и конфигурация</summary><div className="user-details-body"><div className="user-key"><span>Публичный ключ</span><code>{user.public_key}</code></div><div className="user-key"><span>Последнее применение</span><strong>{user.applied_at ? new Date(user.applied_at).toLocaleString("ru-RU") : "Не применён"}</strong></div><div className="user-detail-actions"><button className="text-button inline-button" onClick={() => showConfig(user)} disabled={locked}><FileText size={15} />Показать конфигурацию</button><a className="text-button link-button inline-button" href={vpnUserDownloadUrl(user.id)} download><Download size={15} />Скачать .conf</a><button className="text-button danger inline-button" onClick={() => removeUser(user)} disabled={locked}><Trash2 size={15} />Удалить пользователя</button></div></div></details>
            </article>;
          })}
          {!visibleUsers.length ? <div className="empty-state users-empty"><UsersRound size={30} /><h4>{!hasData ? loading ? "Загружаем пользователей" : "Список недоступен" : !users.length ? "Пока нет пользователей" : "Ничего не найдено"}</h4><p>{!hasData ? "Список появится после получения данных." : !users.length ? "Добавьте устройство, чтобы настроить подключение WireGuard." : "Попробуйте другое имя, IP или фильтр."}</p>{hasData && users.length > 0 && (query || filter !== "all") ? <button className="text-button" onClick={() => { setQuery(""); setFilter("all"); }}>Сбросить поиск и фильтр</button> : null}</div> : null}
        </div>
        <p className="users-footnote">Онлайн — handshake за последние 3 минуты. Трафик накоплен с момента запуска интерфейса на шлюзе.</p>
      </div>
      <div className={`users-apply panel ${pendingChanges ? "has-changes" : ""}`}><div><strong>{pendingChanges ? "Есть сохранённые изменения" : "Применение списка на шлюзе"}</strong><p>Создание, редактирование и удаление сохраняют список в панели. Примените его, чтобы обновить подключения на RU_Cloud.</p></div><button className="secondary-button inline-button" onClick={applyUsers} disabled={locked || !hasData}><Check size={17} />{busy ? "Выполняем…" : "Применить список"}</button></div>
      {dialog?.kind === "form" ? <Modal title={dialog.user ? "Редактировать пользователя" : "Новый пользователь"} onClose={() => setDialog(null)} busy={busy}><form onSubmit={saveUser} className="user-form"><p className="dialog-description">Название поможет узнать устройство в списке.</p><label>Имя пользователя<input autoFocus autoComplete="off" placeholder="Например, iPhone" value={name} onChange={(event) => setName(event.target.value)} disabled={busy} required /></label><label className="user-enabled"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} disabled={busy} /><span><strong>Разрешить подключение</strong><small>Изменение вступит в силу после применения списка.</small></span></label>{dialog.user ? <p className="dialog-description">IP-адрес устройства: <code>{dialog.user.client_ip}</code></p> : null}{formError ? <div className="alert" role="alert"><strong>Не удалось сохранить.</strong><details><summary>Подробнее</summary>{formError}</details></div> : null}<div className="dialog-footer"><button type="button" className="secondary-button" onClick={() => setDialog(null)} disabled={busy}>Отмена</button><button type="submit" className="primary-button" disabled={locked || !name.trim()}>{busy ? "Сохраняем…" : dialog.user ? "Сохранить" : "Создать пользователя"}</button></div></form></Modal> : null}
      {dialog?.kind === "qr" ? <Modal title={`Подключить ${dialog.user.name}`} onClose={() => setDialog(null)}><p className="dialog-description">В приложении WireGuard выберите добавление туннеля и отсканируйте QR-код.</p>{pendingChanges ? <p className="dialog-description">Для новых или изменённых пользователей сначала примените список на шлюзе.</p> : null}<div className="user-qr">{qrError ? <div className="alert" role="alert">Не удалось загрузить QR-код. Закройте окно и попробуйте снова.</div> : <img src={vpnUserQrUrl(dialog.user.id)} alt={`QR-код WireGuard для ${dialog.user.name}`} onError={() => setQrError(true)} />}</div><p className="dialog-description">{dialog.user.client_ip} · {dialog.user.enabled ? "Доступ разрешён в панели" : "Пользователь отключён"}</p><div className="dialog-footer"><button className="secondary-button" onClick={() => setDialog(null)}>Закрыть</button><a className="primary-button link-button inline-button" href={vpnUserDownloadUrl(dialog.user.id)} download><Download size={16} />Скачать .conf</a></div></Modal> : null}
      {dialog?.kind === "config" ? <Modal title={`Конфигурация ${dialog.user.name}`} onClose={() => setDialog(null)} wide><p className="dialog-description">{dialog.config.filename}</p><pre className="user-config">{dialog.config.config}</pre><div className="dialog-footer"><button className="secondary-button" onClick={() => setDialog(null)}>Закрыть</button><a className="primary-button link-button inline-button" href={vpnUserDownloadUrl(dialog.user.id)} download><Download size={16} />Скачать .conf</a></div></Modal> : null}
    </section>
  );
}
