"use client";
import { useClockStore } from "@/lib/store";

export default function NewsFeed() {
  const selectedCountry = useClockStore((s) => s.selectedCountry);
  const worldMap = useClockStore((s) => s.worldMap);
  const country = selectedCountry || "PT";
  const countryData = worldMap.find((c) => c.country_iso === country);

  if (!countryData?.top_news_items?.length) {
    return <div className="text-gray-500 text-sm py-4">No recent events for {country}.</div>;
  }

  return (
    <div className="space-y-3">
      {countryData.top_news_items.slice(0, 5).map((item, i) => (
        <div key={i} className="flex gap-3 p-3 bg-[#111] border border-[#222] rounded-lg">
          <span className="text-gray-500 text-sm font-mono w-4 shrink-0">{i + 1}</span>
          <div>
            <p className="text-sm text-gray-200">{item.headline}</p>
            {item.source_url && (
              <a href={item.source_url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-gray-500 hover:text-gray-400 mt-1 inline-block">
                Source ↗
              </a>
            )}
          </div>
        </div>
      ))}
      {countryData.llm_context_paragraph && (
        <div className="mt-4 p-4 bg-[#111] border-l-2 border-orange-500 rounded">
          <p className="text-sm text-gray-300">{countryData.llm_context_paragraph}</p>
        </div>
      )}
    </div>
  );
}
