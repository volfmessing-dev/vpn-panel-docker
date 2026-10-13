import { useEffect, useRef } from "react";
import { startAutoRefresh } from "../lib/autoRefresh";

export function useAutoRefresh(refresh: () => Promise<void>, enabled: boolean, scope: string) {
  const callback = useRef(refresh);
  callback.current = refresh;
  useEffect(() => {
    if (!enabled) return;
    return startAutoRefresh(() => callback.current(), {
      now: Date.now,
      visible: () => document.visibilityState === "visible",
      schedule: (run, delay) => window.setTimeout(run, delay),
      cancel: timer => window.clearTimeout(timer as number),
      onVisibility: run => { document.addEventListener("visibilitychange", run); return () => document.removeEventListener("visibilitychange", run); },
    });
  }, [enabled, scope]);
}
