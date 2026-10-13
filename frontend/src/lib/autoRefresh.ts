export interface PollEnvironment {
  now: () => number;
  visible: () => boolean;
  schedule: (callback: () => void, delay: number) => unknown;
  cancel: (timer: unknown) => void;
  onVisibility: (callback: () => void) => () => void;
}

/** One pending timer/request, with a full interval after each completed request. */
export function startAutoRefresh(refresh: () => Promise<void>, env: PollEnvironment, interval = 60000) {
  let stopped = false;
  let running = false;
  let timer: unknown;
  let due = env.now() + interval;
  function clear() { if (timer !== undefined) env.cancel(timer); timer = undefined; }
  function schedule() {
    clear();
    if (!stopped && !running && env.visible()) timer = env.schedule(() => { timer = undefined; void tick(); }, Math.max(0, due - env.now()));
  }
  async function tick() {
    if (stopped || running || !env.visible()) return;
    running = true;
    try { await refresh(); } catch { /* The data owner displays its request error. */ }
    finally { running = false; due = env.now() + interval; schedule(); }
  }
  const unsubscribe = env.onVisibility(schedule);
  schedule();
  return () => { stopped = true; clear(); unsubscribe(); };
}

export type RefreshPage = "dashboard" | "nodes" | "cloud-tunnels" | "users" | "topology" | "traffic-policy" | "bypass-list";
export const refreshResources = {
  dashboard: ["nodes", "topology", "tunnels", "users", "bypass", "cloud"],
  nodes: ["nodes", "tunnels", "cloud"],
  "cloud-tunnels": ["nodes", "users", "cloud"],
  users: ["users", "cloud"],
  topology: ["nodes", "tunnels", "users", "cloud"],
  "traffic-policy": ["nodes"],
  "bypass-list": [],
} as const;
