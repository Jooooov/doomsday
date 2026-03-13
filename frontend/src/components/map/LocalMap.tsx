"use client";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { api, type POI } from "@/lib/api";

// POI category config — keys match backend poi_service.py categories
const POI_TYPES: Record<string, { label: string; color: string; emoji: string }> = {
  health:     { label: "Saúde",        color: "#dc2626", emoji: "✚" },
  water:      { label: "Água Potável", color: "#0ea5e9", emoji: "≋" },
  food:       { label: "Alimentação",  color: "#ca8a04", emoji: "⊡" },
  shelter:    { label: "Abrigo",       color: "#7c3aed", emoji: "⌂" },
  security:   { label: "Segurança",    color: "#1d4ed8", emoji: "◉" },
  evacuation: { label: "Combustível",  color: "#ea580c", emoji: "⬆" },
};

function groupPOIs(raw: Record<string, POI[]> | POI[]): Record<string, POI[]> {
  if (Array.isArray(raw)) {
    const g: Record<string, POI[]> = {};
    for (const p of raw) {
      const t = p.type ?? "other";
      (g[t] = g[t] ?? []).push(p);
    }
    return g;
  }
  return raw;
}

interface Props {
  zipCode: string;
  countryCode: string;
}

export default function LocalMap({ zipCode, countryCode }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<import("leaflet").Map | null>(null);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(
    new Set(Object.keys(POI_TYPES))
  );
  const [error, setError] = useState<string | null>(null);
  const [center, setCenter] = useState<[number, number] | null>(null);

  // Geocode zip+country → map center via Nominatim
  useEffect(() => {
    if (!zipCode || !countryCode) return;
    // Strip suffix (4200-369 → 4200) — Nominatim works better with zip prefixes
    const prefix = zipCode.split("-")[0].split(" ")[0];
    const cc = countryCode.toLowerCase();

    const tryGeocode = async () => {
      const attempts = [
        `https://nominatim.openstreetmap.org/search?postalcode=${encodeURIComponent(prefix)}&countrycodes=${cc}&format=json&limit=1`,
        `https://nominatim.openstreetmap.org/search?postalcode=${encodeURIComponent(zipCode)}&countrycodes=${cc}&format=json&limit=1`,
      ];
      for (const url of attempts) {
        try {
          const r = await fetch(url, { headers: { "User-Agent": "DoomsdayPrep/1.0" } });
          const data = await r.json();
          if (data?.[0]) {
            setCenter([parseFloat(data[0].lat), parseFloat(data[0].lon)]);
            return;
          }
        } catch { /* continue */ }
      }
    };
    tryGeocode();
  }, [zipCode, countryCode]);

  const { data, isLoading } = useSWR(
    zipCode && countryCode ? `pois-${zipCode}-${countryCode}` : null,
    () => api.getPOIs(zipCode, countryCode, 5.0, "all"),
    { revalidateOnFocus: false, dedupingInterval: 7 * 24 * 60 * 60 * 1000 }
  );

  // Init map (default center — will be updated by geocode effect)
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    let L: typeof import("leaflet");
    import("leaflet").then((mod) => {
      L = mod.default ?? mod;

      // Fix default icon path issue with Next.js
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
        iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
        shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
      });

      // Leaflet throws if container already initialized (React StrictMode double-mount)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if ((mapRef.current as any)._leaflet_id) {
        mapInstanceRef.current = (mapRef.current as any)._leaflet_map ?? null;
        return;
      }

      const map = L.map(mapRef.current!, {
        center: [38.716, -9.139], // placeholder — geocode effect will fly to real location
        zoom: 13,
        zoomControl: true,
        attributionControl: true,
      });

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '© <a href="https://openstreetmap.org">OpenStreetMap</a>',
        maxZoom: 19,
      }).addTo(map);

      // Apply dark filter via CSS
      const tiles = map.getPane("tilePane");
      if (tiles) {
        tiles.style.filter = "invert(1) hue-rotate(180deg) brightness(0.8) saturate(0.6)";
      }

      // Store ref on both the instance and the DOM node (for StrictMode recovery)
      mapInstanceRef.current = map;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (mapRef.current as any)._leaflet_map = map;
    }).catch((e) => {
      console.warn("[LocalMap] Leaflet init error:", e);
      // Only show error if map isn't already showing
      if (!mapInstanceRef.current) setError("Não foi possível carregar o mapa.");
    });

    return () => {
      mapInstanceRef.current?.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Fly to geocoded center when it becomes available
  useEffect(() => {
    if (!center || !mapInstanceRef.current) return;
    mapInstanceRef.current.flyTo(center, 13, { duration: 1 });
  }, [center]);

  // Add/update markers when data or filter changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !data?.pois) return;

    import("leaflet").then((mod) => {
      const L = mod.default ?? mod;
      const grouped = groupPOIs(data.pois as Record<string, POI[]> | POI[]);
      const bounds: [number, number][] = [];

      // Clear existing markers
      map.eachLayer((layer) => {
        if ((layer as { _doomsday?: boolean })._doomsday) map.removeLayer(layer);
      });

      for (const [type, pois] of Object.entries(grouped)) {
        if (!activeTypes.has(type)) continue;
        const cfg = POI_TYPES[type] ?? { label: type, color: "#59ff59", emoji: "●" };

        for (const poi of pois) {
          const icon = L.divIcon({
            className: "",
            html: `<div style="
              background:${cfg.color};
              color:#fff;
              border-radius:50%;
              width:28px;height:28px;
              display:flex;align-items:center;justify-content:center;
              font-size:13px;
              border:2px solid rgba(255,255,255,0.3);
              box-shadow:0 0 8px ${cfg.color}88;
            ">${cfg.emoji}</div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
          });

          const marker = L.marker([poi.lat, poi.lon], { icon });
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (marker as any)._doomsday = true;
          marker.bindPopup(`
            <div style="font-family:monospace;font-size:12px;min-width:140px">
              <strong>${poi.name || cfg.label}</strong><br/>
              <span style="color:${cfg.color}">${cfg.emoji} ${cfg.label}</span>
            </div>
          `);
          marker.addTo(map);
          bounds.push([poi.lat, poi.lon]);
        }
      }

      if (bounds.length > 0) {
        map.fitBounds(bounds as [number, number][], { padding: [30, 30], maxZoom: 14 });
      }
    });
  }, [data, activeTypes]);

  const toggleType = (type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  if (!zipCode || !countryCode) {
    return (
      <div className="pip-panel p-4 text-center">
        <p className="text-xs tracking-wider" style={{ color: "var(--pip-dim)" }}>
          ▶ Adiciona o teu código postal no perfil para ver recursos locais.
        </p>
        <a href="/profile" className="pip-nav-link text-xs mt-2 inline-block">
          ACTUALIZAR PERFIL
        </a>
      </div>
    );
  }

  return (
    <div className="pip-panel overflow-hidden">
      <div className="px-4 pt-3 pb-2">
        <h2 className="pip-section text-xs mb-2">Recursos Locais — {zipCode}</h2>

        {/* Filter pills */}
        <div className="flex flex-wrap gap-1 mb-2">
          {Object.entries(POI_TYPES).map(([type, cfg]) => (
            <button
              key={type}
              onClick={() => toggleType(type)}
              className="text-[10px] px-2 py-0.5 rounded border transition-all tracking-wider"
              style={{
                borderColor: activeTypes.has(type) ? cfg.color : "var(--border-bright)",
                color: activeTypes.has(type) ? cfg.color : "var(--pip-dim)",
                background: activeTypes.has(type) ? `${cfg.color}18` : "transparent",
              }}
            >
              {cfg.emoji} {cfg.label}
            </button>
          ))}
        </div>

        {isLoading && (
          <p className="text-[10px] animate-pulse mb-1" style={{ color: "var(--pip-dim)" }}>
            A pesquisar recursos próximos...
          </p>
        )}
        {error && (
          <p className="text-[10px] text-red-500 mb-1">⚠ {error}</p>
        )}
        {data?.cached && (
          <p className="text-[10px] opacity-40" style={{ color: "var(--pip-dim)" }}>
            Cache local · Raio 5km
          </p>
        )}
      </div>

      {/* Map */}
      <div ref={mapRef} style={{ height: "280px", width: "100%" }} />

      {/* Leaflet CSS */}
      <style>{`
        @import url("https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css");
        .leaflet-container { background: #050505; }
        .leaflet-popup-content-wrapper {
          background: #111;
          border: 1px solid #1a3a1a;
          color: #59ff59;
          border-radius: 6px;
        }
        .leaflet-popup-tip { background: #111; }
        .leaflet-control-zoom a {
          background: #111 !important;
          color: #59ff59 !important;
          border-color: #1a3a1a !important;
        }
        .leaflet-control-attribution {
          background: rgba(5,5,5,0.8) !important;
          color: #2a6b2a !important;
          font-size: 9px !important;
        }
        .leaflet-control-attribution a { color: #2a6b2a !important; }
      `}</style>
    </div>
  );
}
