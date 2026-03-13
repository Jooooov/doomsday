import WorldMap from "@/components/map/WorldMap";
import NewsFeed from "@/components/clock/NewsFeed";
import CategoryPreview from "@/components/guide/CategoryPreview";
import CTAForm from "@/components/auth/CTAForm";

export default function Home() {
  return (
    <main className="flex flex-col min-h-screen">
      {/* Hero — World Risk Map */}
      <section className="relative h-[60vh] min-h-[400px] border-b border-[#222]">
        <WorldMap />
        <div className="absolute top-4 left-4 z-10 pointer-events-none">
          <h1 className="text-2xl font-bold text-white tracking-tight">Doomsday Prep</h1>
          <p className="text-sm text-gray-400">Regional conflict preparedness · Real-time Doomsday Clock</p>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-4 py-8 w-full">
        <h2 className="text-lg font-semibold text-gray-200 mb-4">Latest Geopolitical Events</h2>
        <NewsFeed />
      </section>

      <section className="max-w-7xl mx-auto px-4 py-8 w-full">
        <h2 className="text-lg font-semibold text-gray-200 mb-4">Preparation Categories</h2>
        <CategoryPreview />
      </section>

      <section className="max-w-2xl mx-auto px-4 py-12 w-full">
        <div className="bg-[#111] border border-[#222] rounded-xl p-8">
          <h2 className="text-xl font-bold text-white mb-2">Get Your Personalized Guide</h2>
          <p className="text-gray-400 mb-6 text-sm">2 questions. Immediate result. Free.</p>
          <CTAForm />
        </div>
      </section>
    </main>
  );
}
