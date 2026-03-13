"use client";
import { useEffect } from "react";
import { registerServiceWorker } from "@/lib/push";
import { useI18nStore } from "@/lib/i18n";

/**
 * Invisible component mounted once in the root layout.
 * - Registers the Service Worker
 * - Loads the initial i18n locale
 */
export default function AppInit() {
  const { locale, load, loaded } = useI18nStore();

  useEffect(() => {
    // Register SW (push notifications)
    registerServiceWorker();

    // Load translations
    if (!loaded) load(locale);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}
