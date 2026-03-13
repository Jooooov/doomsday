"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  getPushPermission,
  getExistingSubscription,
  subscribeToPush,
  unsubscribeFromPush,
  serializeSubscription,
} from "@/lib/push";

type State = "loading" | "unsupported" | "denied" | "off" | "on";

export default function PushToggle() {
  const [state, setState] = useState<State>("loading");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const perm = getPushPermission();
    if (perm === "unsupported") { setState("unsupported"); return; }
    if (perm === "denied")      { setState("denied");      return; }
    getExistingSubscription().then((sub) => setState(sub ? "on" : "off"));
  }, []);

  const toggle = async () => {
    if (state === "on") {
      const sub = await getExistingSubscription();
      if (sub) {
        await unsubscribeFromPush();
        try { await api.unsubscribe(sub.endpoint); } catch { /* ignore */ }
      }
      setState("off");
    } else {
      setState("loading");
      const sub = await subscribeToPush();
      if (!sub) {
        setState(getPushPermission() === "denied" ? "denied" : "off");
        return;
      }
      try { await api.subscribe(serializeSubscription(sub)); } catch { /* ignore */ }
      setState("on");
    }
  };

  if (state === "unsupported") return null;

  const label =
    state === "loading"     ? "A verificar..." :
    state === "denied"      ? "⊘ Notificações bloqueadas" :
    state === "on"          ? "◉ Alertas activos" :
                              "○ Activar alertas";

  const active = state === "on";

  return (
    <button
      onClick={toggle}
      disabled={state === "loading" || state === "denied"}
      className="w-full text-xs px-3 py-2 border rounded transition-all tracking-wider disabled:opacity-40"
      style={{
        borderColor: active ? "var(--pip-green)" : "var(--border-bright)",
        color:       active ? "var(--pip-bright)" : "var(--pip-dim)",
        background:  active ? "rgba(89,255,89,0.08)" : "transparent",
      }}
      title={state === "denied" ? "Desbloqueia notificações nas definições do browser" : ""}
    >
      {label}
    </button>
  );
}
