import { Activity, Cable, GitBranch, ListFilter, Menu, Network, Pause, Play, RefreshCw, Server, Shield, UserRound, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getActiveCloudTunnels, getNodes, getTopology, getTunnels, getVpnBypassStatus, getVpnUsers } from "./api/client";
import { useAutoRefresh } from "./hooks/useAutoRefresh";
import { refreshResources } from "./lib/autoRefresh";
import { Dashboard } from "./pages/Dashboard";
import { Nodes } from "./pages/Nodes";
import { TopologyView } from "./pages/TopologyView";
import { CloudTunnels } from "./pages/CloudTunnels";
import { Users } from "./pages/Users";
import { BypassList } from "./pages/BypassList";
import { TrafficPolicy } from "./pages/TrafficPolicy";
import type { CloudTunnelSnapshot, NodeRecord, Topology, TunnelRecord, VpnBypassStatus, VpnUserRecord } from "./types/api";

type Page = "dashboard" | "nodes" | "cloud-tunnels" | "traffic-policy" | "users" | "bypass-list" | "topology";
const navItems = [
  { id: "dashboard" as const, label: "Обзор", description: "Состояние сети и активный маршрут", icon: Activity },
  { id: "nodes" as const, label: "Узлы", description: "Серверы и сетевые устройства", icon: Server },
  { id: "cloud-tunnels" as const, label: "Туннели", description: "Интерфейсы и подключения", icon: Cable },
  { id: "traffic-policy" as const, label: "Правила трафика", description: "Маршрутизация и направления выхода", icon: GitBranch },
  { id: "users" as const, label: "Пользователи", description: "Подключения WireGuard", icon: UserRound },
  { id: "bypass-list" as const, label: "Список обхода", description: "Домены и адреса для обхода", icon: ListFilter },
  { id: "topology" as const, label: "Схема сети", description: "Узлы, связи и конфигурация туннелей", icon: Network }
];

export function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [menuOpen, setMenuOpen] = useState(false);
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [topology, setTopology] = useState<Topology>({ nodes: [], links: [] });
  const [tunnels, setTunnels] = useState<TunnelRecord[]>([]);
  const [users, setUsers] = useState<VpnUserRecord[]>([]);
  const [bypass, setBypass] = useState<VpnBypassStatus | null>(null);
  const [cloudTunnels, setCloudTunnels] = useState<CloudTunnelSnapshot | null>(null);
  const [errors, setErrors] = useState<Partial<Record<Page, string | null>>>({});
  const [autoEnabled, setAutoEnabled] = useState(true);
  const [visible, setVisible] = useState(document.visibilityState === "visible");
  const [loading, setLoading] = useState(false);
  const [updates, setUpdates] = useState<Partial<Record<Page, number>>>({});
  const updatedAt = updates[page] ?? null;
  const error = errors[page] ?? null;
  const [now, setNow] = useState(Date.now());
  const refreshing = useRef<Promise<void> | null>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLElement>(null);

  async function loadSnapshot(target: Page) {
    setLoading(true);
    try {
      // Only resources required by the selected view are fetched, committed together.
      const loaders = { nodes: getNodes, topology: getTopology, tunnels: getTunnels, users: getVpnUsers, bypass: getVpnBypassStatus, cloud: getActiveCloudTunnels };
      const commits = { nodes: (data: unknown) => setNodes(data as NodeRecord[]), topology: (data: unknown) => setTopology(data as Topology), tunnels: (data: unknown) => setTunnels(data as TunnelRecord[]), users: (data: unknown) => setUsers(data as VpnUserRecord[]), bypass: (data: unknown) => setBypass(data as VpnBypassStatus), cloud: (data: unknown) => setCloudTunnels(data as CloudTunnelSnapshot) };
      const keys = refreshResources[target];
      const results = await Promise.allSettled(keys.map(key => loaders[key]()));
      const failed = results.find(result => result.status === "rejected");
      if (failed?.status === "rejected") throw failed.reason;
      keys.forEach((key, index) => { const result = results[index]; if (result.status === "fulfilled") commits[key](result.value); });
      setUpdates(previous => ({ ...previous, [target]: Date.now() })); setNow(Date.now());
      setErrors(previous => ({ ...previous, [target]: null }));
    } catch (err) {
      setErrors(previous => ({ ...previous, [target]: err instanceof Error ? err.message : "Не удалось получить данные" }));
    } finally {
      setLoading(false);
    }
  }

  async function refresh(target: Page = page) {
    if (refreshing.current) return refreshing.current;
    const request = loadSnapshot(target);
    refreshing.current = request;
    try { await request; }
    finally { refreshing.current = null; }
  }

  async function refreshAfterChange() {
    // A read that started before a mutation may contain the old user list.
    // Finish it, then request a new snapshot after the mutation succeeds.
    if (refreshing.current) await refreshing.current;
    await refresh();
  }

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (refreshing.current) await refreshing.current;
      if (!cancelled && refreshResources[page].length) await refresh(page);
    })();
    return () => { cancelled = true; };
  }, [page]);
  useAutoRefresh(() => refresh(), autoEnabled && page !== "traffic-policy" && page !== "bypass-list", page);
  useEffect(() => {
    const changed = () => { setVisible(document.visibilityState === "visible"); setNow(Date.now()); };
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, []);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 10000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!menuOpen) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    mainRef.current?.setAttribute("inert", "");
    const controls = sidebarRef.current?.querySelectorAll<HTMLButtonElement>("button");
    controls?.[0]?.focus();
    function handleKeys(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
      if (event.key !== "Tab" || !controls?.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    window.addEventListener("keydown", handleKeys);
    return () => {
      window.removeEventListener("keydown", handleKeys);
      document.body.style.overflow = previousOverflow;
      mainRef.current?.removeAttribute("inert");
      previousFocus?.focus();
    };
  }, [menuOpen]);

  const selected = navItems.find((item) => item.id === page)!;
  const age = updatedAt ? Math.max(0, Math.floor((now - updatedAt) / 1000)) : null;
  const stale = Boolean(error) || (age !== null && age >= 180);
  const freshness = age === null ? "Данные ещё не получены" : age < 10 ? "Только что обновлено" : age < 60 ? `Обновлено ${age} сек. назад` : `Обновлено ${Math.floor(age / 60)} мин. назад`;

  return (
    <div className="app-shell">
      {menuOpen ? <button className="menu-backdrop" aria-label="Закрыть меню" onClick={() => setMenuOpen(false)} /> : null}
      <aside ref={sidebarRef} className={`sidebar ${menuOpen ? "is-open" : ""}`} id="main-navigation" aria-label="Основная навигация">
        <div className="brand">
          <span className="brand-mark"><Shield size={24} /></span>
          <div><h1>Bypass Manager</h1><p>Управление сетью</p></div>
          <button className="icon-button menu-close" aria-label="Закрыть меню" onClick={() => setMenuOpen(false)}><X size={20} /></button>
        </div>
        <span className="nav-caption">РАБОЧЕЕ ПРОСТРАНСТВО</span>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            return <button key={item.id} className={page === item.id ? "nav-item active" : "nav-item"} aria-current={page === item.id ? "page" : undefined} onClick={() => { setPage(item.id); setMenuOpen(false); }}><Icon size={18} /><span>{item.label}</span></button>;
          })}
        </nav>
        <div className="sidebar-footer"><Network size={18} /><div><strong>Домашняя сеть</strong><span>WireGuard · AmneziaWG</span></div></div>
      </aside>
      <main ref={mainRef} className="main">
        <header className="topbar">
          <div className="page-heading">
            <button className="icon-button menu-toggle" aria-label="Открыть меню" aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(true)}><Menu size={22} /></button>
            <div><span className="eyebrow">ПАНЕЛЬ УПРАВЛЕНИЯ</span><h2>{selected.label}</h2><p className="page-description">{selected.description}</p></div>
          </div>
          {page !== "traffic-policy" && page !== "bypass-list" ? <div className="refresh-controls"><span className={`freshness ${stale ? "is-stale" : ""}`} role="status"><span className="status-dot" />{loading ? "Получаем данные…" : freshness}</span><button className="secondary-button refresh-button" onClick={() => refresh()} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} /><span>Обновить</span></button></div> : null}
        </header>
        <div className="auto-refresh-bar"><span><span className={`status-dot ${autoEnabled && visible ? "network-good" : ""}`} />{!autoEnabled ? "Автообновление на паузе" : !visible ? "Автообновление ждёт открытия вкладки" : "Автообновление · 60 секунд"}</span><button className="text-button inline-button" onClick={() => setAutoEnabled(value => !value)} aria-pressed={!autoEnabled}>{autoEnabled ? <Pause size={14} /> : <Play size={14} />}{autoEnabled ? "Пауза" : "Продолжить"}</button></div>
        {page !== "traffic-policy" && page !== "bypass-list" ? error ? <div className="alert" role="alert"><strong>Не удалось обновить данные.</strong> {updatedAt ? "Показаны результаты предыдущей проверки. " : "Повторите запрос. "}<details><summary>Подробнее</summary>{error}</details></div> : stale ? <div className="stale-notice">Данные старше трёх минут. Обновите их, чтобы проверить текущее состояние сети.</div> : null : null}
        {page === "dashboard" ? <Dashboard nodes={nodes} links={topology.links} tunnels={tunnels} users={users} bypass={bypass} cloudTunnels={cloudTunnels} now={now} hasData={updatedAt !== null} stale={stale} onNavigate={setPage} /> : null}
        {page === "nodes" ? <Nodes nodes={nodes} tunnels={tunnels} now={now} hasData={updatedAt !== null} stale={stale} cloudTunnels={cloudTunnels} onChanged={refreshAfterChange} /> : null}
        {page === "cloud-tunnels" ? <CloudTunnels snapshot={cloudTunnels} nodes={nodes} users={users} now={now} hasData={updatedAt !== null} stale={stale} loading={loading} /> : null}
        {page === "traffic-policy" ? <TrafficPolicy nodes={nodes} now={now} autoEnabled={autoEnabled} /> : null}
        {page === "users" ? <Users users={users} cloudTunnels={cloudTunnels} now={now} hasData={updatedAt !== null} stale={stale} loading={loading} onChanged={refreshAfterChange} /> : null}
        {page === "bypass-list" ? <BypassList now={now} autoEnabled={autoEnabled} onNavigate={() => setPage("traffic-policy")} /> : null}
        {page === "topology" ? <TopologyView nodes={nodes} tunnels={tunnels} users={users} cloudTunnels={cloudTunnels} now={now} hasData={updatedAt !== null} stale={stale} /> : null}
      </main>
    </div>
  );
}
