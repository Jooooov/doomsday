"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";

function fmt(secs: number) {
  const s = Math.max(0, Math.round(secs));
  const m = Math.floor(s / 60);
  const ss = s % 60;
  return `${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

export default function NavClock() {
  const { data } = useSWR("world-map-nav", api.getWorldMap, { refreshInterval: 60_000 });
  const [secs, setSecs] = useState<number | null>(null);

  useEffect(() => {
    if (!data?.countries?.length) return;
    const avg = data.countries.reduce((sum, c) => sum + c.seconds_to_midnight, 0) / data.countries.length;
    setSecs(avg);
  }, [data]);

  // Tick every second
  useEffect(() => {
    if (secs === null) return;
    const id = setInterval(() => setSecs(s => Math.max(0, (s ?? 0) - 1)), 1000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [secs === null]);

  return (
    <div className="flex flex-col items-center leading-none select-none">
      <span
        className="text-[9px] tracking-[0.25em] uppercase"
        style={{ color: "#7a4a00" }}
      >
        ☢ DOOMSDAY CLOCK
      </span>

      <div
        className="font-fallout text-4xl md:text-5xl tracking-[0.05em] mt-1"
        style={{
          color: "#FFB000",
          animation: "valve-breathe 4s ease-in-out infinite",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {secs === null ? "--:--" : fmt(secs)}
      </div>

      <span
        className="text-[8px] tracking-[0.3em] uppercase mt-0.5"
        style={{ color: "#7a4a00" }}
      >
        MIN · SEC · TO MIDNIGHT
      </span>
    </div>
  );
}
