"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { CATEGORY_META } from "@/lib/categories";
import { useAuthStore } from "@/lib/store";
import { api } from "@/lib/api";

const CAT_DESCRIPTION: Record<string, string> = {
  water:
    "Sem água potável, a sobrevivência mede-se em dias. Armazena 2 litros por pessoa por dia, aprende a purificar água de fontes alternativas e mantém recipientes adequados sempre cheios.",
  food:
    "Uma despensa bem abastecida dá autonomia nas primeiras semanas. Prioriza alimentos não-perecíveis com boa densidade calórica e considera as necessidades especiais do teu agregado.",
  shelter:
    "A tua casa é o teu primeiro abrigo. Sabe como reforçá-la, como desligar as utilidades em emergência e onde te abrigar se precisares de evacuar.",
  health:
    "Kit de primeiros socorros completo, medicação de reserva e conhecimentos básicos de triagem podem salvar vidas quando os hospitais estão sobrecarregados.",
  communication:
    "Em crise, a informação é poder. Um rádio a pilhas, uma lista de contactos em papel e um ponto de encontro familiar definem a diferença entre caos e coordenação.",
  evacuation:
    "Ter uma mochila de 72h pronta e conhecer 2 rotas de saída da tua área permite agir em minutos quando o tempo é crítico.",
  energy:
    "Sem eletricidade, muito colapsa rapidamente. Lanternas, pilhas e uma estratégia de recarga mantêm-te operacional durante cortes prolongados.",
  security:
    "Em situações de crise, manter a tua localização segura e discreta protege o teu agregado de ameaças oportunistas.",
  documentation:
    "Documentos originais e cópias seguras de apólices, identificações e registos médicos são insubstituíveis numa evacuação forçada.",
  mental_health:
    "A preparação psicológica é tão importante quanto a física. Rotinas, comunicação aberta e atividades estruturadas ajudam a gerir o stress coletivo em situações prolongadas.",
  armed_conflict:
    "Conflito ativo requer planos de abrigo, discrição e rotas de saída do país. Regista-te nas bases de dados consulares e mantém os documentos acessíveis.",
  family_coordination:
    "Um plano familiar acordado e praticado previamente funciona mesmo quando as comunicações falham. Cada membro deve saber o que fazer sem precisar de ser instruído.",
};

function itemKey(category: string, text: string) {
  return `${category}::${text}`;
}

function readChecked(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem("doomsday_checked");
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set();
  } catch { return new Set(); }
}

export default function CategoryPreview() {
  const { user, _hydrated } = useAuthStore();
  const router = useRouter();
  const [selected, setSelected] = useState<string | null>(null);

  const { data: guide } = useSWR(user ? "my-guide" : null, api.getMyGuide, {
    revalidateOnFocus: false,
  });

  const selectedMeta = CATEGORY_META.find((c) => c.id === selected);
  const selectedSection = selected ? guide?.content?.[selected] : undefined;

  const checked = _hydrated ? readChecked() : new Set<string>();

  return (
    <>
      {/* Category grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {CATEGORY_META.map((cat) => {
          const items = guide?.content?.[cat.id]?.items ?? [];
          const done = items.filter((it) => checked.has(itemKey(cat.id, it.text))).length;
          const hasGuide = items.length > 0;

          return (
            <button
              key={cat.id}
              onClick={() => setSelected(cat.id)}
              className="pip-panel p-4 text-left transition-all hover:shadow-[0_0_20px_rgba(89,255,89,0.08)] active:scale-[0.98]"
              style={{ cursor: "pointer" }}
            >
              {/* Icon */}
              <div
                className="text-3xl leading-none mb-3 flex items-center justify-center rounded-lg"
                style={{
                  width: 48, height: 48,
                  background: `${cat.color}18`,
                  border: `1.5px solid ${cat.color}55`,
                  boxShadow: `0 0 12px ${cat.color}22`,
                }}
              >
                {cat.icon}
              </div>

              {/* Label */}
              <div className="text-xs uppercase tracking-[0.12em] mb-1 font-mono" style={{ color: cat.color }}>
                {cat.label}
              </div>

              {/* Preview text */}
              <div className="text-xs leading-relaxed mb-2" style={{ color: "var(--pip-dim)" }}>
                {cat.preview}
              </div>

              {/* Progress (only if guide loaded) */}
              {hasGuide && (
                <div className="mt-auto">
                  <div className="flex justify-between text-[9px] font-mono mb-1"
                    style={{ color: done === items.length ? cat.color : "var(--pip-dim)" }}>
                    <span>{done === items.length ? "✓ CONCLUÍDO" : `${done}/${items.length} feitos`}</span>
                  </div>
                  <div className="h-0.5 rounded-full" style={{ background: "#1a1a1a" }}>
                    <div className="h-full rounded-full transition-all"
                      style={{ width: `${items.length > 0 ? (done / items.length) * 100 : 0}%`, background: cat.color }} />
                  </div>
                </div>
              )}

              {/* CTA hint */}
              {!hasGuide && (
                <div className="text-[9px] font-mono mt-1" style={{ color: "#1a3a1a" }}>
                  clica para saber mais →
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Modal overlay */}
      {selected && selectedMeta && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(4px)" }}
          onClick={() => setSelected(null)}
        >
          <div
            className="relative w-full max-w-lg rounded-xl overflow-hidden"
            style={{ background: "#0a0f0a", border: `1.5px solid ${selectedMeta.color}44`, maxHeight: "85vh", overflowY: "auto" }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-6 py-5 border-b" style={{ borderColor: "#1a3a1a" }}>
              <div className="flex items-center gap-4">
                <div
                  className="text-4xl flex items-center justify-center rounded-xl shrink-0"
                  style={{
                    width: 56, height: 56,
                    background: `${selectedMeta.color}18`,
                    border: `1.5px solid ${selectedMeta.color}66`,
                    boxShadow: `0 0 16px ${selectedMeta.color}33`,
                  }}
                >
                  {selectedMeta.icon}
                </div>
                <div className="flex-1">
                  <h3 className="font-mono uppercase tracking-widest text-sm font-bold" style={{ color: selectedMeta.color }}>
                    {selectedMeta.label}
                  </h3>
                  <p className="text-xs mt-0.5" style={{ color: "var(--pip-dim)" }}>
                    Protocolo de preparação
                  </p>
                </div>
                <button onClick={() => setSelected(null)}
                  className="text-xl leading-none opacity-40 hover:opacity-100 transition-opacity"
                  style={{ color: "var(--pip-green)" }}>✕</button>
              </div>
            </div>

            {/* Description */}
            <div className="px-6 py-4">
              <p className="text-sm leading-relaxed" style={{ color: "#a3c9a3" }}>
                {CAT_DESCRIPTION[selected] ?? selectedMeta.preview}
              </p>
            </div>

            {/* Content: logged in with guide */}
            {user && selectedSection?.items?.length ? (
              <div className="px-6 pb-2">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-mono uppercase tracking-widest" style={{ color: selectedMeta.color }}>
                    O que fazer
                  </p>
                  {(() => {
                    const total = selectedSection.items.length;
                    const done = selectedSection.items.filter((it) =>
                      checked.has(itemKey(selected, it.text))
                    ).length;
                    return (
                      <span className="text-xs font-mono" style={{ color: done === total ? selectedMeta.color : "var(--pip-dim)" }}>
                        {done}/{total} {done === total ? "✓" : ""}
                      </span>
                    );
                  })()}
                </div>
                <div className="space-y-2 mb-4">
                  {selectedSection.items.map((item, i) => {
                    const done = checked.has(itemKey(selected, item.text));
                    return (
                      <div key={i} className="flex items-start gap-3 rounded-lg px-3 py-2.5"
                        style={{ background: done ? "#0d0d0d" : "#111", border: "1px solid #1a1a1a", opacity: done ? 0.5 : 1 }}>
                        <span className="mt-0.5 text-base">{done ? "✅" : "⬜"}</span>
                        <div className="flex-1">
                          <p className="text-xs leading-snug"
                            style={{ color: done ? "var(--pip-dim)" : "var(--pip-green)", textDecoration: done ? "line-through" : "none" }}>
                            {item.text}
                          </p>
                          {item.quantity && (
                            <span className="text-[10px] font-mono opacity-50">{item.quantity} {item.unit}</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
                {selectedSection.disclaimer && (
                  <p className="text-[10px] opacity-40 mb-4 italic" style={{ color: "var(--pip-dim)" }}>
                    {selectedSection.disclaimer}
                  </p>
                )}
              </div>
            ) : user && guide?.status === "pending" ? (
              <div className="px-6 pb-5 text-center">
                <p className="text-xs mb-3" style={{ color: "var(--pip-dim)" }}>
                  Ainda não geraste o teu guia personalizado.
                </p>
                <button onClick={() => router.push("/dashboard")}
                  className="pip-btn pip-btn-solid text-xs tracking-widest">
                  GERAR GUIA →
                </button>
              </div>
            ) : !user ? (
              <div className="px-6 pb-5">
                <div className="rounded-lg p-4 mb-4 text-center" style={{ background: "#111", border: "1px solid #1a3a1a" }}>
                  <p className="text-xs mb-1" style={{ color: "var(--pip-green)" }}>
                    Cria o teu perfil para ver o teu guia personalizado e acompanhar o progresso.
                  </p>
                </div>
                <div className="flex gap-3">
                  <button onClick={() => router.push("/register")}
                    className="flex-1 pip-btn pip-btn-solid text-xs tracking-widest">
                    CRIAR PERFIL
                  </button>
                  <button onClick={() => router.push("/login")}
                    className="flex-1 pip-btn text-xs tracking-widest">
                    ENTRAR
                  </button>
                </div>
              </div>
            ) : null}

            {/* Go to guide CTA */}
            {user && (
              <div className="px-6 pb-5">
                <button
                  onClick={() => router.push(`/dashboard?cat=${selected}`)}
                  className="w-full py-2.5 rounded-lg text-xs font-mono uppercase tracking-widest transition-all"
                  style={{
                    background: `${selectedMeta.color}18`,
                    border: `1px solid ${selectedMeta.color}55`,
                    color: selectedMeta.color,
                  }}
                >
                  {selectedMeta.icon} Ver no Guia de Sobrevivência →
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
