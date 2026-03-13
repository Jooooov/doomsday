"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import DoomsdayClock from "@/components/clock/DoomsdayClock";

interface Props { countryIso: string; onClose: () => void; }

export default function CountryModal({ countryIso, onClose }: Props) {
  const { data, isLoading } = useSWR(`country-${countryIso}`, () => api.getCountryDetail(countryIso));

  return (
    <div className="absolute inset-0 bg-black/70 flex items-center justify-center z-20" onClick={onClose}>
      <div className="bg-[#111] border border-[#222] rounded-xl p-6 max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold">{countryIso}</h2>
            <p className="text-xs text-gray-500 uppercase tracking-wider">Doomsday Clock</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl">×</button>
        </div>

        {isLoading ? (
          <div className="text-gray-500 animate-pulse py-8 text-center text-sm">Loading...</div>
        ) : data ? (
          <>
            <div className="flex justify-center mb-6">
              <DoomsdayClock
                secondsToMidnight={data.seconds_to_midnight}
                riskLevel={data.risk_level as "green" | "yellow" | "orange" | "red"}
                size={160}
              />
            </div>
            {data.llm_context_paragraph && (
              <p className="text-sm text-gray-300 mb-4 border-l-2 border-gray-600 pl-3">
                {data.llm_context_paragraph}
              </p>
            )}
            {data.top_news_items && data.top_news_items.length > 0 && (
              <div className="space-y-2 mb-4">
                <h3 className="text-xs text-gray-500 uppercase tracking-wider">Recent Events</h3>
                {data.top_news_items.slice(0, 3).map((item, i) => (
                  <p key={i} className="text-sm text-gray-400">• {item.headline}</p>
                ))}
              </div>
            )}
            <a href="/register"
              className="block w-full text-center py-2 px-4 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors">
              Get Your Preparation Guide →
            </a>
          </>
        ) : null}
      </div>
    </div>
  );
}
