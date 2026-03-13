"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import useSWR from "swr";
import { api, type GuideSection } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { CATEGORY_META } from "@/lib/categories";
import PushToggle from "@/components/ui/PushToggle";

const TIMELINES = [
  { id: "7d",   label: "7 DIAS",  sublabel: "imediato",   color: "#ef4444", bg: "#450a0a" },
  { id: "30d",  label: "30 DIAS", sublabel: "curto prazo", color: "#f97316", bg: "#431407" },
  { id: "180d", label: "6 MESES", sublabel: "médio prazo", color: "#eab308", bg: "#422006" },
  { id: "360d", label: "1 ANO",   sublabel: "longo prazo", color: "#22c55e", bg: "#052e16" },
] as const;

function priorityToTimeline(priority?: number): string {
  if (priority === 1) return "7d";
  if (priority === 2) return "30d";
  if (priority === 3) return "180d";
  return "360d";
}

const LocalMap = dynamic(() => import("@/components/map/LocalMap"), { ssr: false });

const CATEGORY_PT: Record<string, string> = {
  water: "Água", food: "Alimentação", shelter: "Abrigo", health: "Saúde",
  communication: "Comunicação", evacuation: "Evacuação", energy: "Energia",
  security: "Segurança", documentation: "Documentação", mental_health: "Saúde Mental",
  armed_conflict: "Conflito Armado", family_coordination: "Coordenação Familiar",
};

export default function DashboardPage() {
  const { user, clearAuth, _hydrated } = useAuthStore();
  const router = useRouter();
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState<{ category: string; index: number; total: number } | null>(null);
  const [genWarning, setGenWarning] = useState<string | null>(null);
  const [guideView, setGuideView] = useState<"accordion" | "timeline">("accordion");

  useEffect(() => { if (_hydrated && !user) router.push("/login"); }, [user, router, _hydrated]);

  const { data: guide, mutate: mutateGuide } = useSWR(user ? "my-guide" : null, api.getMyGuide);
  const { data: group } = useSWR(user ? "my-group" : null, api.getMyGroup);
  const { data: checklist } = useSWR(user ? "group-checklist" : null, api.getGroupChecklist);

  if (!user) return null;

  // Profile completeness — required before generating guide
  const missingFields: string[] = [];
  if (!user.country_code) missingFields.push("país");
  if (!user.household_size) missingFields.push("nº de pessoas");
  if (!user.housing_type) missingFields.push("tipo de habitação");
  const profileComplete = missingFields.length === 0;

  const handleGenerateGuide = async () => {
    setGenerating(true);
    setGenProgress(null);
    setGenWarning(null);
    try {
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
          } catch { /* ignore parse errors */ }
        }
      }
      if (hadErrors) setGenWarning("Alguns conteúdos usaram modo de contingência.");
      mutateGuide();
    } catch (err) {
      setGenWarning("Falha na ligação ao servidor.");
    } finally {
      setGenerating(false);
      setGenProgress(null);
    }
  };

  return (
    <div className="min-h-screen">
      {/* ── Navbar ── */}
      <nav className="border-b border-[#1a3a1a] px-5 py-3 flex justify-between items-center bg-[#050505]">
        <div>
          <a href="/" className="pip-glow pip-flicker font-fallout uppercase tracking-[0.15em] text-xl">
            ☢ DOOMSDAY PREP
          </a>
          <span className="hidden md:inline text-[10px] tracking-[0.2em] ml-3 uppercase"
            style={{ color: "var(--pip-dim)" }}>// TERMINAL DO SOBREVIVENTE</span>
        </div>
        <div className="flex gap-3 text-sm">
          <Link href="/" className="pip-nav-link text-xs">[ MAPA ]</Link>
          <Link href="/profile" className="pip-nav-link text-xs">[ PERFIL ]</Link>
          <button onClick={() => { clearAuth(); router.push("/"); }}
            className="pip-nav-link text-xs">[ SAIR ]</button>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 py-6 grid lg:grid-cols-3 gap-6">
        {/* ── Guia — 2/3 ── */}
        <div className="lg:col-span-2">
          <div className="flex items-center gap-3 mb-4">
            <h1 className="font-fallout uppercase tracking-[0.15em] text-xl md:text-2xl pip-glow mb-0">
              ☢ GUIA DE SOBREVIVÊNCIA
            </h1>
            {guide?.badge && (
              <span className="pip-badge-warn">{guide.badge}</span>
            )}
          </div>

          {genWarning && (
            <div className="pip-badge-warn flex items-center gap-2 mb-3 p-2">
              ⚠ {genWarning}
            </div>
          )}

          {!guide || guide.status === "pending" ? (
            <div className="pip-panel p-8 text-center space-y-4">
              <p className="tracking-[0.15em] uppercase text-sm pip-glow">
                ▶ SEM GUIA GERADO
              </p>
              {!profileComplete ? (
                <>
                  <p className="text-sm tracking-wider" style={{ color: "var(--pip-dim)" }}>
                    Perfil incompleto. Completa o teu perfil antes de gerar o guia.
                  </p>
                  <p className="pip-badge-danger inline-flex items-center gap-1">
                    ⚠ Em falta: {missingFields.join(", ")}
                  </p>
                  <div>
                    <a href="/profile" className="pip-btn pip-btn-solid text-sm tracking-widest">
                      COMPLETAR PERFIL
                    </a>
                  </div>
                </>
              ) : generating ? (
                <div className="space-y-3 text-left">
                  <p className="text-sm tracking-wider cursor-blink" style={{ color: "var(--pip-green)" }}>
                    {genProgress
                      ? `▶ COMPILANDO: ${CATEGORY_PT[genProgress.category] || genProgress.category} (${genProgress.index + 1}/${genProgress.total})`
                      : "▶ INICIALIZANDO PROTOCOLO..."}
                  </p>
                  <div className="pip-bar">
                    <div className="pip-bar-fill"
                      style={{ width: genProgress ? `${((genProgress.index + 1) / genProgress.total) * 100}%` : "5%" }} />
                  </div>
                </div>
              ) : (
                <button onClick={handleGenerateGuide} className="pip-btn pip-btn-solid text-sm tracking-widest">
                  COMPILAR GUIA DE SOBREVIVÊNCIA
                </button>
              )}
            </div>
          ) : guide.content ? (
            <>
              {/* View toggle */}
              <div className="flex gap-2 mb-4">
                {(["accordion", "timeline"] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setGuideView(v)}
                    className="text-[10px] px-3 py-1.5 border tracking-widest uppercase transition-all rounded"
                    style={{
                      borderColor: guideView === v ? "var(--pip-green)" : "#1a3a1a",
                      color: guideView === v ? "var(--pip-green)" : "var(--pip-dim)",
                      background: guideView === v ? "#59ff5912" : "transparent",
                    }}
                  >
                    {v === "accordion" ? "⊞ CATEGORIAS" : "◈ TIMELINE"}
                  </button>
                ))}
              </div>
              {guideView === "accordion"
                ? <GuideAccordion content={guide.content} />
                : <GuideTimeline content={guide.content} />}
            </>
          ) : null}
        </div>

        {/* ── Sidebar — 1/3 ── */}
        <div className="space-y-4">
          {/* Grupo familiar */}
          <div className="pip-panel p-4">
            <h2 className="pip-section text-xs mb-3">Grupo Familiar</h2>
            {group && "group_id" in group ? (
              <div className="text-sm space-y-1" style={{ color: "var(--pip-green)" }}>
                <p className="tracking-wider">{group.member_count} membros</p>
                {group.is_admin && (
                  <p className="text-xs break-all" style={{ color: "var(--pip-dim)" }}>
                    ▶ Convite: {group.invite_link}
                  </p>
                )}
              </div>
            ) : (
              <button onClick={async () => {
                const g = await api.createGroup();
                alert(`Partilha: ${window.location.origin}${g.invite_link}`);
              }} className="pip-btn text-xs w-full">
                CRIAR GRUPO
              </button>
            )}
          </div>

          {/* Mapa local */}
          {user.zip_code && user.country_code && (
            <LocalMap zipCode={user.zip_code} countryCode={user.country_code} />
          )}

          {/* Checklist */}
          {checklist?.items && checklist.items.length > 0 && (
            <div className="pip-panel p-4">
              <h2 className="pip-section text-xs mb-3">Checklist Familiar</h2>
              <div className="space-y-2">
                {checklist.items.slice(0, 8).map((item) => (
                  <label key={item.id} className="flex items-start gap-2 text-xs cursor-pointer"
                    style={{ color: item.status === "complete" ? "var(--pip-dim)" : "var(--pip-green)" }}>
                    <input type="checkbox" checked={item.status === "complete"} readOnly
                      className="mt-0.5 pip-check" />
                    <span className={item.status === "complete" ? "line-through opacity-50" : ""}>
                      {item.text}
                      {item.calculated_quantity && (
                        <span className="ml-1 opacity-50">({item.calculated_quantity} {item.quantity_unit})</span>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Push notifications */}
          <div className="pip-panel p-4">
            <h2 className="pip-section text-xs mb-3">Alertas de Emergência</h2>
            <PushToggle />
            <p className="text-[10px] mt-2 opacity-40 tracking-wider" style={{ color: "var(--pip-dim)" }}>
              Notificação imediata quando o patamar de risco muda no teu país.
            </p>
          </div>

          {/* RGPD */}
          <div className="pip-panel p-4">
            <h2 className="pip-section text-xs mb-3">Privacidade RGPD</h2>
            <div className="flex flex-col gap-2">
              <a href="/api/users/me/export" className="pip-nav-link text-xs">
                ▶ Exportar dados (JSON)
              </a>
              <button onClick={async () => {
                if (confirm("Eliminar conta permanentemente?")) {
                  await api.deleteAccount();
                  clearAuth();
                  router.push("/");
                }
              }} className="pip-btn pip-btn-danger text-xs text-left">
                ELIMINAR CONTA
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function GuideAccordion({ content }: { content: Record<string, GuideSection> }) {
  const order = CATEGORY_META.map((c) => c.id);
  const sorted = [...Object.entries(content)].sort(
    ([a], [b]) => order.indexOf(a) - order.indexOf(b)
  );
  return (
    <div className="space-y-2">
      {sorted.map(([category, section]) => {
        const meta = CATEGORY_META.find((c) => c.id === category);
        const color = meta?.color ?? "#59ff59";
        return (
          <details key={category} className="pip-panel group">
            <summary className="px-4 py-3 cursor-pointer text-sm flex items-center gap-3 uppercase tracking-wider select-none"
              style={{ color: "var(--pip-green)" }}>
              {/* Colored category badge */}
              <span style={{
                background: color,
                color: "#fff",
                borderRadius: "50%",
                width: 22, height: 22, minWidth: 22,
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                fontSize: 11,
                boxShadow: `0 0 8px ${color}66`,
                opacity: 0.85,
              }} className="group-open:opacity-100 transition-opacity">
                {meta?.icon}
              </span>
              <span className="flex-1">{section?.title || meta?.label || category.replace("_", " ")}</span>
              <span className="text-xs opacity-40 group-open:opacity-80 font-mono">
                {section?.items?.length ?? 0} ITENS
              </span>
            </summary>
            <div className="px-4 pb-4 pt-2 space-y-2 border-t border-[#1a3a1a]">
              {section?.items?.map((item, i) => {
                const tl = TIMELINES.find(t => t.id === priorityToTimeline(item.priority));
                return (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span style={{ color: tl?.color ?? "#59ff59" }} className="mt-0.5 font-mono text-xs shrink-0">▸</span>
                    <span style={{ color: "var(--pip-green)" }}>
                      {item.text}
                      {item.quantity && (
                        <span className="ml-2 opacity-50 text-xs font-mono">
                          [{item.quantity} {item.unit}]
                        </span>
                      )}
                    </span>
                    {tl && (
                      <span className="ml-auto shrink-0 text-[9px] font-mono px-1.5 py-0.5 rounded"
                        style={{ color: tl.color, background: tl.bg, border: `1px solid ${tl.color}44` }}>
                        {tl.label}
                      </span>
                    )}
                  </div>
                );
              })}
              {section?.disclaimer && (
                <p className="disclaimer mt-3 text-xs">{section.disclaimer}</p>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}

function GuideTimeline({ content }: { content: Record<string, GuideSection> }) {
  const [activeTab, setActiveTab] = useState<string>("7d");

  const allItems = Object.entries(content).flatMap(([cat, section]) => {
    const meta = CATEGORY_META.find((c) => c.id === cat);
    return (section?.items ?? []).map((item) => ({
      ...item,
      category: cat,
      catLabel: meta?.label?.split(" ")[0] ?? cat,
      catIcon: meta?.icon ?? "▸",
      catColor: meta?.color ?? "#59ff59",
      timeline: priorityToTimeline(item.priority),
    }));
  });

  const activeTl = TIMELINES.find((t) => t.id === activeTab)!;
  const tabItems = allItems.filter((i) => i.timeline === activeTab);

  return (
    <div>
      {/* Timeline tab bar */}
      <div className="grid grid-cols-4 gap-1 mb-4">
        {TIMELINES.map((tl) => {
          const count = allItems.filter((i) => i.timeline === tl.id).length;
          const active = activeTab === tl.id;
          return (
            <button
              key={tl.id}
              onClick={() => setActiveTab(tl.id)}
              className="py-2 px-1 text-center border transition-all rounded"
              style={{
                borderColor: active ? tl.color : "#1a3a1a",
                background: active ? tl.bg : "transparent",
                boxShadow: active ? `0 0 12px ${tl.color}33` : "none",
              }}
            >
              <div className="font-mono font-bold text-xs tracking-widest"
                style={{ color: active ? tl.color : "var(--pip-dim)" }}>
                {tl.label}
              </div>
              <div className="text-[8px] tracking-wide mt-0.5 uppercase"
                style={{ color: active ? tl.color : "var(--pip-dim)", opacity: 0.7 }}>
                {tl.sublabel}
              </div>
              <div className="text-[10px] font-mono font-bold mt-1"
                style={{ color: active ? tl.color : "#1a3a1a" }}>
                {count}
              </div>
            </button>
          );
        })}
      </div>

      {/* Header */}
      <p className="text-[10px] mb-3 tracking-widest font-mono uppercase"
        style={{ color: activeTl.color }}>
        ▶ {tabItems.length} ACÇÕES · {activeTl.sublabel.toUpperCase()}
      </p>

      {/* Items */}
      {tabItems.length === 0 ? (
        <p className="text-xs opacity-40 text-center py-4" style={{ color: "var(--pip-dim)" }}>
          Sem itens para este período.
        </p>
      ) : (
        <div className="space-y-1.5">
          {tabItems.map((item, i) => (
            <div key={i}
              className="flex items-center gap-3 rounded px-3 py-2"
              style={{ background: "#0a0a0a", border: "1px solid #1a1a1a" }}>
              {/* Category icon badge */}
              <div style={{
                background: item.catColor,
                color: "#fff",
                borderRadius: "50%",
                width: 26, height: 26, minWidth: 26,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12,
                boxShadow: `0 0 8px ${item.catColor}55`,
                flexShrink: 0,
              }}>
                {item.catIcon}
              </div>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <p className="text-xs leading-snug" style={{ color: "var(--pip-green)" }}>
                  {item.text}
                </p>
                {item.quantity && (
                  <span className="text-[10px] font-mono opacity-50">
                    {item.quantity} {item.unit}
                  </span>
                )}
              </div>

              {/* Category label chip */}
              <span className="text-[9px] font-mono uppercase tracking-wide shrink-0 px-1.5 py-0.5 rounded"
                style={{
                  color: item.catColor,
                  background: `${item.catColor}18`,
                  border: `1px solid ${item.catColor}44`,
                }}>
                {item.catLabel}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
