"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type UserPreferences } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { useI18nStore, type Locale } from "@/lib/i18n";
import useSWR from "swr";

const COUNTRIES = [
  { code: "PT", name: "Portugal" }, { code: "US", name: "United States" },
  { code: "GB", name: "United Kingdom" }, { code: "DE", name: "Germany" },
  { code: "FR", name: "France" }, { code: "ES", name: "Spain" },
  { code: "BR", name: "Brazil" }, { code: "IT", name: "Italy" },
  { code: "NL", name: "Netherlands" }, { code: "PL", name: "Poland" },
  { code: "AU", name: "Australia" }, { code: "CA", name: "Canada" },
  { code: "JP", name: "Japan" }, { code: "UA", name: "Ukraine" },
  { code: "RU", name: "Russia" }, { code: "CN", name: "China" },
  { code: "IL", name: "Israel" }, { code: "IN", name: "India" },
  { code: "SE", name: "Sweden" }, { code: "TR", name: "Turkey" },
  { code: "MX", name: "Mexico" }, { code: "AR", name: "Argentina" },
  { code: "ZA", name: "South Africa" }, { code: "KR", name: "South Korea" },
  { code: "NG", name: "Nigeria" }, { code: "SA", name: "Saudi Arabia" },
  { code: "PK", name: "Pakistan" }, { code: "EG", name: "Egypt" },
  { code: "NO", name: "Norway" }, { code: "CH", name: "Switzerland" },
];

const HOUSING_TYPES = [
  { value: "apartment_urban", label: "Apartamento urbano" },
  { value: "apartment_rural", label: "Apartamento rural" },
  { value: "house_urban", label: "Moradia urbana" },
  { value: "house_rural", label: "Moradia rural" },
];

const PET_TYPES = [
  { value: "cão", label: "🐕 Cão" },
  { value: "gato", label: "🐈 Gato" },
  { value: "pássaro", label: "🐦 Pássaro" },
  { value: "peixe", label: "🐠 Peixe" },
  { value: "coelho", label: "🐇 Coelho" },
  { value: "roedor", label: "🐹 Roedor" },
  { value: "réptil", label: "🦎 Réptil" },
  { value: "outro", label: "🐾 Outro" },
];

const inputCls = "pip-input pip-select w-full text-sm";
const labelCls = "block text-xs uppercase tracking-widest mb-1";
const sectionCls = "pip-panel p-4 space-y-4";
const sectionTitleCls = "pip-section text-xs mb-3";

const isApartment = (type: string) => type.startsWith("apartment");

const CATEGORY_PT: Record<string, string> = {
  water: "Água", food: "Alimentação", shelter: "Abrigo", health: "Saúde",
  communication: "Comunicação", evacuation: "Evacuação", energy: "Energia",
  security: "Segurança", documentation: "Documentação", mental_health: "Saúde Mental",
  armed_conflict: "Conflito Armado", family_coordination: "Coordenação Familiar",
};

export default function ProfilePage() {
  const { user: storeUser, setAuth, token, _hydrated } = useAuthStore();
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState<{ category: string; index: number; total: number } | null>(null);
  const [genDone, setGenDone] = useState(false);
  const [genWarning, setGenWarning] = useState<string | null>(null);

  // Fetch fresh user data from API — store may be stale (old login without preferences)
  const { data: freshUser, mutate: mutateMe } = useSWR(
    _hydrated && storeUser ? "profile-me" : null,
    api.getMe,
  );
  const user = freshUser ?? storeUser;

  const [form, setForm] = useState({
    country_code: "",
    zip_code: "",
    household_size: 2,
    housing_type: "apartment_urban",
    has_vehicle: false,
    language: "pt",
    health_data_consent: false,
  });

  const [prefs, setPrefs] = useState<UserPreferences>({
    budget_level: "médio",
    has_children: false,
    children_count: 0,
    pet_types: [],
    has_elderly: false,
    has_mobility_issues: false,
    floor_number: null,
  });

  // Redirect if not logged in
  useEffect(() => {
    if (_hydrated && !storeUser) router.push("/login");
  }, [_hydrated, storeUser, router]);

  // Populate form once we have fresh API data
  useEffect(() => {
    if (!user) return;
    setForm({
      country_code: user.country_code || "PT",
      zip_code: user.zip_code || "",
      household_size: user.household_size || 2,
      housing_type: user.housing_type || "apartment_urban",
      has_vehicle: user.has_vehicle ?? false,
      language: user.language || "pt",
      health_data_consent: user.health_data_consent ?? false,
    });
    setPrefs({
      budget_level: user.preferences?.budget_level ?? "médio",
      has_children: user.preferences?.has_children ?? false,
      children_count: user.preferences?.children_count ?? 0,
      pet_types: user.preferences?.pet_types ?? [],
      has_elderly: user.preferences?.has_elderly ?? false,
      has_mobility_issues: user.preferences?.has_mobility_issues ?? false,
      floor_number: user.preferences?.floor_number ?? null,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [freshUser?.id, !!freshUser]);

  const togglePet = (pet: string) => {
    const current = prefs.pet_types ?? [];
    setPrefs({
      ...prefs,
      pet_types: current.includes(pet) ? current.filter((p) => p !== pet) : [...current, pet],
    });
  };

  const hasPets = (prefs.pet_types?.length ?? 0) > 0;

  const { setLocale } = useI18nStore();

  const saveProfile = async () => {
    const updated = await api.updateProfile({ ...form, preferences: prefs });
    if (token) setAuth(token, updated);
    await mutateMe(updated, { revalidate: false }); // refresh SWR cache instantly
    // Apply language change immediately
    if (form.language && (form.language === "pt" || form.language === "en")) {
      await setLocale(form.language as Locale);
    }
    return updated;
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    try {
      await saveProfile();
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Erro ao guardar perfil";
      setSaveError(msg.includes("401") || msg.includes("Invalid") ? "Sessão expirada — faz login novamente" : msg);
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateGuide = async () => {
    setGenerating(true);
    setGenProgress(null);
    setGenDone(false);
    setGenWarning(null);
    try {
      // Save first so the latest profile is used
      await saveProfile();
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/guides/me/generate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("doomsday_token")}` },
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 429) {
          setGenWarning("Limite de gerações atingido (20/hora). Tenta mais tarde.");
        } else {
          setGenWarning(err.detail || err.error || `Erro ${res.status} ao gerar o guia.`);
        }
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let hadErrors = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "category_start") {
              setGenProgress({ category: evt.category, index: evt.index ?? 0, total: evt.total ?? 12 });
            } else if (evt.type === "category_error") {
              hadErrors = true;
            } else if (evt.type === "error") {
              setGenWarning(evt.message || "Erro na geração.");
            }
          } catch { /* ignore */ }
        }
      }
      if (hadErrors) setGenWarning("Alguns conteúdos usaram modo de contingência.");
      setGenDone(true);
    } catch {
      setGenWarning("Falha na ligação ao servidor.");
    } finally {
      setGenerating(false);
      setGenProgress(null);
    }
  };

  const profileComplete = !!(form.country_code && form.household_size && form.housing_type);

  if (!storeUser) return null;

  return (
    <div className="min-h-screen">
      <nav className="border-b border-[#1a3a1a] px-5 py-3 flex justify-between items-center bg-[#050505]">
        <a href="/" className="pip-glow pip-flicker font-fallout uppercase tracking-[0.15em] text-xl">
          ☢ DOOMSDAY PREP
        </a>
        <a href="/dashboard" className="pip-nav-link text-xs">[ ← TERMINAL ]</a>
      </nav>

      <div className="max-w-lg mx-auto px-4 py-8">
        <h1 className="font-fallout uppercase tracking-[0.15em] text-2xl md:text-3xl pip-glow mb-6">
          ☢ PERFIL DO SOBREVIVENTE
        </h1>

        {!freshUser && (
          <div className="text-xs tracking-[0.2em] mb-4 cursor-blink" style={{ color: "var(--pip-dim)" }}>
            ▶ A CARREGAR DADOS
          </div>
        )}

        <form onSubmit={handleSave} className="space-y-5">

          {/* LOCALIZAÇÃO */}
          <div className={sectionCls}>
            <p className={sectionTitleCls}>Localização</p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>País <span className="text-red-500">*</span></label>
                <select value={form.country_code}
                  onChange={(e) => setForm({ ...form, country_code: e.target.value })}
                  className={inputCls}>
                  {COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Código postal</label>
                <input value={form.zip_code}
                  onChange={(e) => setForm({ ...form, zip_code: e.target.value })}
                  placeholder="ex. 1000-001"
                  className={inputCls} />
              </div>
            </div>
          </div>

          {/* AGREGADO */}
          <div className={sectionCls}>
            <p className={sectionTitleCls}>Agregado</p>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>Nº de pessoas <span className="text-red-500">*</span></label>
                <select value={form.household_size}
                  onChange={(e) => setForm({ ...form, household_size: Number(e.target.value) })}
                  className={inputCls}>
                  {[1,2,3,4,5,6,7,8].map((n) => (
                    <option key={n} value={n}>{n} {n === 1 ? "pessoa" : "pessoas"}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelCls}>Habitação <span className="text-red-500">*</span></label>
                <select value={form.housing_type}
                  onChange={(e) => setForm({ ...form, housing_type: e.target.value })}
                  className={inputCls}>
                  {HOUSING_TYPES.map((h) => <option key={h.value} value={h.value}>{h.label}</option>)}
                </select>
              </div>
            </div>

            {/* Floor — only for apartments */}
            {isApartment(form.housing_type) && (
              <div>
                <label className={labelCls}>Andar</label>
                <input
                  type="number" min={0} max={50}
                  value={prefs.floor_number ?? ""}
                  onChange={(e) => setPrefs({ ...prefs, floor_number: e.target.value === "" ? null : Number(e.target.value) })}
                  placeholder="ex. 3"
                  className={inputCls} />
              </div>
            )}

            <div className="space-y-3">
              {/* Vehicle */}
              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={form.has_vehicle}
                  onChange={(e) => setForm({ ...form, has_vehicle: e.target.checked })}
                  className="pip-check" />
                <span className="text-sm" style={{ color: "var(--pip-green)" }}>Tenho veículo</span>
              </label>

              {/* Children */}
              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={prefs.has_children ?? false}
                  onChange={(e) => setPrefs({ ...prefs, has_children: e.target.checked, children_count: e.target.checked ? (prefs.children_count || 1) : 0 })}
                  className="pip-check" />
                <span className="text-sm" style={{ color: "var(--pip-green)" }}>Tenho crianças no agregado</span>
              </label>
              {prefs.has_children && (
                <div className="ml-6">
                  <label className={labelCls}>Número de crianças</label>
                  <select value={prefs.children_count ?? 1}
                    onChange={(e) => setPrefs({ ...prefs, children_count: Number(e.target.value) })}
                    className={inputCls}>
                    {[1,2,3,4,5].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </div>
              )}

              {/* Elderly */}
              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={prefs.has_elderly ?? false}
                  onChange={(e) => setPrefs({ ...prefs, has_elderly: e.target.checked })}
                  className="pip-check" />
                <span className="text-sm" style={{ color: "var(--pip-green)" }}>Tenho idosos (+65 anos) no agregado</span>
              </label>

              {/* Mobility */}
              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={prefs.has_mobility_issues ?? false}
                  onChange={(e) => setPrefs({ ...prefs, has_mobility_issues: e.target.checked })}
                  className="pip-check" />
                <span className="text-sm" style={{ color: "var(--pip-green)" }}>Alguém com mobilidade reduzida</span>
              </label>
            </div>

            {/* Pets */}
            <div>
              <p className={labelCls}>Animais de estimação</p>
              <div className="grid grid-cols-4 gap-2 mt-1">
                {PET_TYPES.map((pet) => {
                  const selected = prefs.pet_types?.includes(pet.value);
                  return (
                    <button key={pet.value} type="button"
                      onClick={() => togglePet(pet.value)}
                      className={`px-2 py-2 text-xs border text-center transition-all ${
                        selected
                          ? "border-[var(--pip-green)] text-[var(--pip-bright)] bg-[rgba(89,255,89,0.1)] shadow-[0_0_8px_rgba(89,255,89,0.3)]"
                          : "border-[var(--border-bright)] text-[var(--pip-dim)] hover:border-[var(--pip-dim)] hover:text-[var(--pip-green)]"
                      }`}>
                      {pet.label}
                    </button>
                  );
                })}
              </div>
              {hasPets && (
                <p className="text-xs text-gray-600 mt-2">
                  Selecionado: {prefs.pet_types?.join(", ")}
                </p>
              )}
            </div>
          </div>

          {/* PREFERÊNCIAS */}
          <div className={sectionCls}>
            <p className={sectionTitleCls}>Preferências</p>

            <div>
              <label className={labelCls}>Orçamento para preparação</label>
              <div className="flex gap-2">
                {([
                  { value: "baixo", label: "Baixo", sub: "< €100" },
                  { value: "médio", label: "Médio", sub: "€100–500" },
                  { value: "alto",  label: "Alto",  sub: "> €500" },
                ] as const).map(({ value, label, sub }) => (
                  <button key={value} type="button"
                    onClick={() => setPrefs({ ...prefs, budget_level: value })}
                    className={`flex-1 py-2 text-xs border transition-all flex flex-col items-center gap-0.5 ${
                      prefs.budget_level === value
                        ? "border-[var(--pip-green)] text-[var(--pip-bright)] bg-[rgba(89,255,89,0.1)] shadow-[0_0_8px_rgba(89,255,89,0.25)]"
                        : "border-[var(--border-bright)] text-[var(--pip-dim)] hover:border-[var(--pip-dim)]"
                    }`}>
                    <span className="tracking-wider">{label}</span>
                    <span className="opacity-60">{sub}</span>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className={labelCls}>Idioma</label>
              <select value={form.language}
                onChange={(e) => setForm({ ...form, language: e.target.value })}
                className={inputCls}>
                <option value="pt">Português</option>
                <option value="en">English</option>
              </select>
            </div>

            <label className="flex items-start gap-3 cursor-pointer">
              <input type="checkbox" checked={form.health_data_consent}
                onChange={(e) => setForm({ ...form, health_data_consent: e.target.checked })}
                className="accent-red-500 mt-0.5" />
              <span className="text-sm" style={{ color: "var(--pip-green)" }}>
                Consinto armazenar dados de saúde para personalizar o guia
                <span className="block text-xs text-gray-500 mt-0.5">RGPD: guardados de forma encriptada, elimináveis a qualquer momento</span>
              </span>
            </label>
          </div>

          <p className="text-xs tracking-wider" style={{ color: "var(--pip-dim)" }}>
            ▶ campos com <span style={{ color: "var(--danger)" }}>*</span> são obrigatórios para gerar o guia
          </p>

          {saveError && (
            <div className="pip-badge-danger flex items-center gap-2 p-2 text-xs">
              ⚠ {saveError}
              {saveError.includes("expirada") && (
                <a href="/login" className="underline ml-2">Entrar →</a>
              )}
            </div>
          )}

          <div className="flex gap-3">
            <button type="submit" disabled={saving || generating}
              className="pip-btn flex-1 py-2.5 text-sm tracking-[0.12em] disabled:opacity-40">
              {saving ? "GUARDANDO..." : saved ? "GUARDADO ✓" : "GUARDAR"}
            </button>

            {profileComplete && (
              <button type="button" disabled={generating || saving}
                onClick={handleGenerateGuide}
                className="pip-btn pip-btn-solid flex-1 py-2.5 text-sm tracking-[0.1em] disabled:opacity-40">
                {generating ? "COMPILANDO..." : "GUARDAR E COMPILAR GUIA"}
              </button>
            )}
          </div>

          {/* Guide generation progress */}
          {generating && (
            <div className="space-y-2 pt-1">
              <p className="text-sm tracking-wider cursor-blink" style={{ color: "var(--pip-green)" }}>
                {genProgress
                  ? `▶ COMPILANDO: ${CATEGORY_PT[genProgress.category] || genProgress.category} (${genProgress.index + 1}/${genProgress.total})`
                  : "▶ GUARDANDO PERFIL..."}
              </p>
              <div className="pip-bar">
                <div className="pip-bar-fill"
                  style={{ width: genProgress ? `${((genProgress.index + 1) / genProgress.total) * 100}%` : "5%" }} />
              </div>
            </div>
          )}

          {genWarning && (
            <div className="pip-badge-warn flex items-center gap-2 p-2">
              ⚠ {genWarning}
            </div>
          )}

          {genDone && (
            <div className="pip-badge-ok flex items-center justify-between p-3">
              <span>▶ GUIA COMPILADO COM SUCESSO</span>
              <a href="/dashboard" className="pip-nav-link underline text-xs">
                VER NO TERMINAL →
              </a>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
