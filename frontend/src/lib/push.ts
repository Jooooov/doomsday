/**
 * Web Push utilities — registration + subscription management.
 * Requires NEXT_PUBLIC_VAPID_PUBLIC_KEY in env.
 */

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";

function urlBase64ToUint8Array(base64String: string): ArrayBuffer {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr.buffer;
}

/** Register the service worker. Call once on app init. */
export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return null;
  try {
    const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    return reg;
  } catch (e) {
    console.warn("[SW] Registration failed:", e);
    return null;
  }
}

/** Check current push permission state. */
export function getPushPermission(): NotificationPermission | "unsupported" {
  if (typeof window === "undefined" || !("Notification" in window)) return "unsupported";
  return Notification.permission;
}

/** Returns existing subscription or null. */
export async function getExistingSubscription(): Promise<PushSubscription | null> {
  if (!("serviceWorker" in navigator)) return null;
  const reg = await navigator.serviceWorker.ready;
  return reg.pushManager.getSubscription();
}

/**
 * Subscribe to push notifications.
 * Returns the subscription object or null on failure/denied.
 */
export async function subscribeToPush(): Promise<PushSubscription | null> {
  if (!VAPID_PUBLIC_KEY) {
    console.warn("[Push] NEXT_PUBLIC_VAPID_PUBLIC_KEY not set");
    return null;
  }
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return null;

  const reg = await navigator.serviceWorker.ready;
  try {
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    });
    return sub;
  } catch (e) {
    console.warn("[Push] Subscribe failed:", e);
    return null;
  }
}

/** Unsubscribe from push notifications. */
export async function unsubscribeFromPush(): Promise<boolean> {
  const sub = await getExistingSubscription();
  if (!sub) return true;
  return sub.unsubscribe();
}

/** Serialise a PushSubscription for the backend API. */
export function serializeSubscription(sub: PushSubscription) {
  const raw = sub.toJSON();
  return {
    endpoint: sub.endpoint,
    keys: {
      p256dh: raw.keys?.p256dh ?? "",
      auth: raw.keys?.auth ?? "",
    },
  };
}
