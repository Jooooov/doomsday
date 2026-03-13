const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("doomsday_token") : null;

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  getWorldMap: () => apiFetch<WorldMapResponse>("/api/clock/world"),
  getCountryDetail: (iso: string) => apiFetch<CountryDetail>(`/api/clock/country/${iso}`),
  getTop5: (iso: string) => apiFetch<Top5Response>(`/api/clock/top5/${iso}`),
  register: (email: string, password: string, language = "pt") =>
    apiFetch<AuthResponse>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password, language }) }),
  login: (email: string, password: string) =>
    apiFetch<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  getMe: () => apiFetch<UserProfile>("/api/users/me"),
  updateProfile: (data: Partial<UserProfile>) =>
    apiFetch<UserProfile>("/api/users/me", { method: "PATCH", body: JSON.stringify(data) }),
  exportData: () => apiFetch<unknown>("/api/users/me/export"),
  deleteAccount: () => apiFetch<unknown>("/api/users/me", { method: "DELETE" }),
  getMyGuide: () => apiFetch<GuideResponse>("/api/guides/me"),
  createGroup: () => apiFetch<GroupResponse>("/api/groups/create", { method: "POST" }),
  joinGroup: (token: string) => apiFetch<GroupResponse>(`/api/groups/join/${token}`, { method: "POST" }),
  getMyGroup: () => apiFetch<GroupDetail>("/api/groups/me"),
  getGroupChecklist: () => apiFetch<ChecklistResponse>("/api/groups/me/checklist"),
  getPOIs: (zip: string, country: string, radius: number, category: string) =>
    apiFetch<POIResponse>(`/api/map/pois?zip_code=${zip}&country_code=${country}&radius_km=${radius}&category=${category}`),
  subscribe: (sub: PushSubscriptionData) =>
    apiFetch<unknown>("/api/notifications/subscribe", { method: "POST", body: JSON.stringify(sub) }),
};

export interface WorldMapResponse { countries: CountryScore[]; generated_at: string; }
export interface CountryScore {
  country_iso: string; seconds_to_midnight: number;
  risk_level: "green" | "yellow" | "orange" | "red";
  llm_context_paragraph: string | null; top_news_items: NewsItem[] | null;
  last_updated: string; is_propagated: boolean;
}
export interface CountryDetail extends CountryScore {}
export interface NewsItem { headline: string; source_url: string; }
export interface Top5Response { items: PrepItem[]; risk_level: string; country: string; }
export interface PrepItem { text: string; category: string; priority: number; quantity?: number; unit?: string; }
export interface AuthResponse { access_token: string; token_type: string; user: UserProfile; }
export interface UserProfile {
  id: string; email: string; country_code: string | null;
  zip_code: string | null; household_size: number | null;
  housing_type: string | null; language: string; family_group_id: string | null;
}
export interface GuideResponse { status: "current" | "updating" | "pending"; content?: Record<string, GuideSection>; badge?: string; }
export interface GuideSection { title: string; items: PrepItem[]; disclaimer?: string; }
export interface GroupResponse { group_id: string; invite_link: string; admin: boolean; is_admin: boolean; }
export interface GroupDetail extends GroupResponse { member_count: number; members: { id: string; email: string }[]; }
export interface ChecklistResponse { items: ChecklistItem[]; }
export interface ChecklistItem {
  id: string; text: string; category: string;
  status: "not_started" | "partial" | "complete"; progress: number;
  assigned_to: string | null; calculated_quantity: number | null;
  quantity_unit: string | null; is_new_recommendation: boolean;
}
export interface POIResponse { pois: Record<string, POI[]> | POI[]; cached: boolean; }
export interface POI { id: number; lat: number; lon: number; name: string; type: string; }
export interface PushSubscriptionData { endpoint: string; keys: { p256dh: string; auth: string }; }
