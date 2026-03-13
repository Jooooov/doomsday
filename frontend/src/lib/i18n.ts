/**
 * Lightweight i18n — no external dependency.
 * Translations live in /public/locales/{lang}.json (offline LLM-generated).
 * Language preference stored in localStorage + Zustand store.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Locale = "pt" | "en";
export const LOCALES: Locale[] = ["pt", "en"];
export const LOCALE_LABELS: Record<Locale, string> = { pt: "Português", en: "English" };

// ── Zustand store ────────────────────────────────────────────────────────────
interface I18nStore {
  locale: Locale;
  messages: Record<string, unknown>;
  loaded: boolean;
  setLocale: (locale: Locale) => Promise<void>;
  load: (locale: Locale) => Promise<void>;
}

export const useI18nStore = create<I18nStore>()(
  persist(
    (set, get) => ({
      locale: "pt",
      messages: {},
      loaded: false,

      load: async (locale: Locale) => {
        try {
          const res = await fetch(`/locales/${locale}.json`);
          const messages = await res.json();
          set({ messages, loaded: true, locale });
        } catch {
          set({ loaded: true });
        }
      },

      setLocale: async (locale: Locale) => {
        if (locale === get().locale && get().loaded) return;
        set({ loaded: false });
        await get().load(locale);
      },
    }),
    {
      name: "doomsday-locale",
      partialize: (s) => ({ locale: s.locale }),
    }
  )
);

// ── Translation function ─────────────────────────────────────────────────────
function resolve(messages: Record<string, unknown>, key: string): string {
  const parts = key.split(".");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let cur: any = messages;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object") return key;
    cur = cur[p];
  }
  return typeof cur === "string" ? cur : key;
}

/**
 * t("dashboard.title")
 * t("clock.seconds_to_midnight")
 * t("group.members", { n: 3 })    → "3 membros"
 */
export function makeT(messages: Record<string, unknown>) {
  return (key: string, vars?: Record<string, string | number>): string => {
    let str = resolve(messages, key);
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        str = str.replace(`{{${k}}}`, String(v));
      }
    }
    return str;
  };
}

// ── React hook ───────────────────────────────────────────────────────────────
import { useEffect } from "react";

export function useI18n() {
  const { locale, messages, loaded, setLocale, load } = useI18nStore();

  // Load on mount if not yet loaded
  useEffect(() => {
    if (!loaded) load(locale);
  }, [loaded, locale, load]);

  const t = makeT(messages as Record<string, unknown>);
  return { t, locale, setLocale, loaded };
}
