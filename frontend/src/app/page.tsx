import WorldMap from "@/components/map/WorldMap";
import NewsFeed from "@/components/clock/NewsFeed";
import CategoryPreview from "@/components/guide/CategoryPreview";
import CTAForm from "@/components/auth/CTAForm";

export default function Home() {
  return (
    <main className="flex flex-col min-h-screen">

      {/* ── Navbar ── */}
      <nav className="flex items-center justify-between px-5 py-2 border-b border-[#1f1f1f] bg-[#080808] z-20 relative">
        <div>
          <span className="text-2xl text-green-400 tracking-widest uppercase">☢ DOOMSDAY PREP</span>
          <span className="hidden md:inline text-xs text-gray-600 ml-4 tracking-wider">
            // WORLD THREAT ASSESSMENT TERMINAL
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm tracking-wider">
          <a href="/login"  className="text-gray-500 hover:text-green-400 transition-colors uppercase">[ Login ]</a>
          <a href="/register" className="text-green-400 border border-green-400/40 hover:border-green-400 px-3 py-1 transition-colors uppercase">
            Criar Conta
          </a>
        </div>
      </nav>

      {/* ── World Risk Map — maximum space ── */}
      <section className="relative flex-1" style={{ minHeight: "calc(100vh - 44px)" }}>
        <WorldMap />
      </section>

      {/* ── Below-the-fold sections ── */}
      <section className="max-w-7xl mx-auto px-4 py-10 w-full border-t border-[#1a1a1a]">
        <h2 className="text-xl text-green-400 tracking-widest uppercase mb-5">
          // Últimos Eventos Geopolíticos
        </h2>
        <NewsFeed />
      </section>

      <section className="max-w-7xl mx-auto px-4 py-10 w-full border-t border-[#1a1a1a]">
        <h2 className="text-xl text-green-400 tracking-widest uppercase mb-5">
          // Categorias de Preparação
        </h2>
        <CategoryPreview />
      </section>

      <section className="max-w-2xl mx-auto px-4 py-12 w-full">
        <div className="bg-[#0d0d0d] border border-green-400/20 rounded-none p-8">
          <h2 className="text-2xl text-green-400 tracking-widest uppercase mb-1">
            Obter Guia Personalizado
          </h2>
          <p className="text-gray-500 mb-6 text-sm tracking-wider">
            2 perguntas. Resultado imediato. Gratuito.
          </p>
          <CTAForm />
        </div>
      </section>

    </main>
  );
}
