import WorldMap from "@/components/map/WorldMap";
import NewsFeed from "@/components/clock/NewsFeed";
import CategoryPreview from "@/components/guide/CategoryPreview";
import NavClock from "@/components/clock/NavClock";

export default function Home() {
  return (
    <main className="flex flex-col min-h-screen pip-power-on">

      {/* ── Navbar ── */}
      <nav className="flex items-center justify-between px-5 py-3 border-b border-[#1a3a1a] bg-[#050505] z-20 relative">
        {/* Logo */}
        <div className="flex flex-col">
          <span
            className="pip-glow pip-tick font-fallout uppercase tracking-[0.2em] text-3xl md:text-4xl"
            style={{ color: "var(--pip-bright)", lineHeight: 1 }}
          >
            ☢ DOOMSDAY PREP
          </span>
          <span className="text-[10px] tracking-[0.25em] uppercase mt-0.5 hidden md:block"
            style={{ color: "var(--pip-dim)" }}>
            ▶ WORLD THREAT ASSESSMENT TERMINAL v2.0
          </span>
        </div>

        {/* Doomsday Clock */}
        <div className="hidden md:block">
          <NavClock />
        </div>

        {/* Nav actions */}
        <div className="flex items-center gap-3 text-sm">
          <a href="/login" className="pip-nav-link text-sm hidden sm:block">[ Login ]</a>
          <a href="/register"
            className="pip-btn pip-btn-solid font-fallout text-sm tracking-widest">
            CRIAR PERFIL
          </a>
        </div>
      </nav>

      {/* ── World Risk Map — full viewport ── */}
      <section className="relative flex-1" style={{ minHeight: "calc(100vh - 60px)" }}>
        <WorldMap />
      </section>

      {/* ── Últimos Eventos ── */}
      <section className="max-w-7xl mx-auto px-4 py-10 w-full border-t border-[#1a3a1a]">
        <h2 className="font-fallout uppercase tracking-[0.2em] text-2xl md:text-3xl pip-glow mb-1">
          ☢ INTEL DE AMEAÇAS GLOBAIS
        </h2>
        <p className="text-xs tracking-[0.2em] uppercase mb-6" style={{ color: "var(--pip-dim)" }}>
          ▶ FEED EM TEMPO REAL — ACTUALIZADO AUTOMATICAMENTE
        </p>
        <NewsFeed />
      </section>

      {/* ── Categorias de Preparação ── */}
      <section className="max-w-7xl mx-auto px-4 py-10 w-full border-t border-[#1a3a1a]">
        <h2 className="font-fallout uppercase tracking-[0.2em] text-2xl md:text-3xl pip-glow mb-1">
          ☢ PROTOCOLOS DE SOBREVIVÊNCIA
        </h2>
        <p className="text-xs tracking-[0.2em] uppercase mb-6" style={{ color: "var(--pip-dim)" }}>
          ▶ 12 MÓDULOS DE PREPARAÇÃO — VAULT-TEC CERTIFIED
        </p>
        <CategoryPreview />
      </section>

      {/* ── Footer CTA ── */}
      <section className="border-t border-[#1a3a1a] py-16 text-center">
        <p className="font-fallout uppercase tracking-[0.2em] text-3xl md:text-5xl pip-glow pip-glow-pulse mb-3">
          ☢ PREPARE-SE PARA O APOCALIPSE ☢
        </p>
        <p className="text-sm mb-8 tracking-[0.1em]" style={{ color: "var(--pip-dim)" }}>
          Cria o teu perfil de sobrevivente e recebe o teu guia de sobrevivência personalizado por IA.
        </p>
        <a href="/register" className="pip-btn pip-btn-solid font-fallout tracking-[0.15em] text-lg px-10 py-4">
          INICIAR PROTOCOLO DE SOBREVIVÊNCIA
        </a>
      </section>

    </main>
  );
}
