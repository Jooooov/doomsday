"use client";
import { useEffect, useState, useCallback } from "react";
import useSWR from "swr";
import { ComposableMap, Geographies, Geography, ZoomableGroup } from "react-simple-maps";
import { api, type CountryScore } from "@/lib/api";
import { useClockStore } from "@/lib/store";
import CountryModal from "./CountryModal";

const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

const NUM2ISO: Record<string, string> = {
  "4":"AF","8":"AL","12":"DZ","24":"AO","32":"AR","36":"AU","40":"AT","50":"BD",
  "56":"BE","64":"BT","68":"BO","76":"BR","100":"BG","116":"KH","120":"CM",
  "124":"CA","140":"CF","144":"LK","152":"CL","156":"CN","170":"CO","180":"CD",
  "188":"CR","191":"HR","192":"CU","196":"CY","203":"CZ","204":"BJ","208":"DK",
  "214":"DO","218":"EC","818":"EG","222":"SV","231":"ET","246":"FI","250":"FR",
  "266":"GA","276":"DE","288":"GH","300":"GR","320":"GT","324":"GN","332":"HT",
  "340":"HN","348":"HU","356":"IN","360":"ID","364":"IR","368":"IQ","372":"IE",
  "376":"IL","380":"IT","388":"JM","392":"JP","400":"JO","398":"KZ","404":"KE",
  "408":"KP","410":"KR","414":"KW","418":"LA","422":"LB","430":"LR","434":"LY",
  "442":"LU","450":"MG","454":"MW","458":"MY","484":"MX","504":"MA","508":"MZ",
  "516":"NA","524":"NP","528":"NL","554":"NZ","558":"NI","562":"NE","566":"NG",
  "578":"NO","586":"PK","591":"PA","598":"PG","600":"PY","604":"PE","608":"PH",
  "616":"PL","620":"PT","634":"QA","642":"RO","643":"RU","646":"RW","682":"SA",
  "686":"SN","694":"SL","706":"SO","710":"ZA","724":"ES","729":"SD","752":"SE",
  "756":"CH","760":"SY","764":"TH","792":"TR","800":"UG","804":"UA","784":"AE",
  "826":"GB","840":"US","858":"UY","860":"UZ","862":"VE","704":"VN","887":"YE",
  "894":"ZM","716":"ZW","31":"AZ","51":"AM","112":"BY","233":"EE","268":"GE",
  "428":"LV","440":"LT","498":"MD","807":"MK","496":"MN","499":"ME","688":"RS",
  "703":"SK","705":"SI","795":"TM","630":"PR",
};

const FILL: Record<string, string> = {
  green:"#14532d", yellow:"#713f12", orange:"#7c2d12", red:"#450a0a", default:"#171717",
};
const FILL_HOVER: Record<string, string> = {
  green:"#16a34a", yellow:"#ca8a04", orange:"#ea580c", red:"#dc2626", default:"#262626",
};
const RISK_LABEL: Record<string, string> = {
  green:"Baixo risco", yellow:"Risco moderado", orange:"Risco elevado", red:"Risco crítico",
};

interface Tip { x:number; y:number; iso:string; risk:string; seconds:number; }

export default function WorldMap() {
  const { data, isLoading } = useSWR("world-map", api.getWorldMap, { refreshInterval: 30*60*1000 });
  const { setWorldMap, selectCountry, selectedCountry } = useClockStore();
  const [tip, setTip] = useState<Tip|null>(null);
  const [pos, setPos] = useState<{coordinates:[number,number];zoom:number}>({coordinates:[0,15],zoom:1});

  useEffect(() => { if (data?.countries) setWorldMap(data.countries); }, [data, setWorldMap]);

  const scoreMap = useCallback((): Record<string, CountryScore> => {
    const m: Record<string, CountryScore> = {};
    for (const c of data?.countries ?? []) m[c.country_iso] = c;
    return m;
  }, [data])();

  if (isLoading) return (
    <div className="w-full h-full flex items-center justify-center bg-[#0a0a0a]">
      <p className="text-gray-500 text-sm animate-pulse">A carregar mapa de risco mundial...</p>
    </div>
  );

  return (
    <div className="relative w-full h-full bg-[#050505] select-none overflow-hidden">
      <ComposableMap
        projection="geoNaturalEarth1"
        style={{ width:"100%", height:"100%" }}
        projectionConfig={{ scale:155, center:[0,15] }}
      >
        <ZoomableGroup
          zoom={pos.zoom} center={pos.coordinates}
          onMoveEnd={({coordinates,zoom}) => setPos({coordinates:coordinates as [number,number],zoom})}
          minZoom={1} maxZoom={8}
        >
          <Geographies geography={GEO_URL}>
            {({ geographies }) => geographies.map((geo) => {
              const numId = String(geo.id);
              const iso2  = NUM2ISO[numId] ?? NUM2ISO[String(parseInt(numId,10))];
              const score = iso2 ? scoreMap[iso2] : undefined;
              const risk  = score?.risk_level ?? "default";
              return (
                <Geography key={geo.rsmKey} geography={geo}
                  style={{
                    default:{ fill:FILL[risk],       stroke:"#0a0a0a", strokeWidth:0.35, outline:"none" },
                    hover:  { fill:FILL_HOVER[risk], stroke:"#0a0a0a", strokeWidth:0.35, outline:"none", cursor:score?"pointer":"default" },
                    pressed:{ fill:FILL_HOVER[risk], stroke:"#0a0a0a", strokeWidth:0.35, outline:"none" },
                  }}
                  onMouseEnter={(e) => { if(score&&iso2) setTip({x:e.clientX,y:e.clientY,iso:iso2,risk,seconds:score.seconds_to_midnight}); }}
                  onMouseMove={(e)  => { if(tip) setTip(t=>t?{...t,x:e.clientX,y:e.clientY}:null); }}
                  onMouseLeave={()  => setTip(null)}
                  onClick={()       => { if(iso2&&score){setTip(null);selectCountry(iso2);} }}
                />
              );
            })}
          </Geographies>
        </ZoomableGroup>
      </ComposableMap>

      {tip && (
        <div className="fixed z-30 pointer-events-none bg-[#111]/95 border border-[#333] rounded-lg px-3 py-2 text-xs shadow-xl"
          style={{left:tip.x+14, top:tip.y-54}}>
          <p className="font-bold text-white text-sm">{tip.iso}</p>
          <p className="text-gray-400">{tip.seconds.toFixed(1)}s até meia-noite</p>
          <p className={`font-semibold mt-0.5 ${
            tip.risk==="green"?"text-green-400":tip.risk==="yellow"?"text-yellow-400":tip.risk==="orange"?"text-orange-400":"text-red-400"
          }`}>{RISK_LABEL[tip.risk]??tip.risk}</p>
        </div>
      )}

      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/70 backdrop-blur-sm border border-[#222] rounded-xl px-4 py-2 flex gap-4">
        {(["red","orange","yellow","green"] as const).map((l) => (
          <div key={l} className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm border border-white/10" style={{background:FILL_HOVER[l]}}/>
            <span className="text-xs text-gray-400 whitespace-nowrap">{RISK_LABEL[l]}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-sm" style={{background:FILL.default, border:"1px solid #333"}}/>
          <span className="text-xs text-gray-600">Sem dados</span>
        </div>
      </div>

      <p className="absolute top-3 right-3 text-[10px] text-gray-700 pointer-events-none">
        Scroll → zoom · Arrasta → mover · Clica → detalhes
      </p>
      <p className="absolute top-3 left-3 text-[10px] text-gray-600">
        {data?.countries.length ?? 0} países monitorizados
      </p>

      {selectedCountry && (
        <CountryModal countryIso={selectedCountry} onClose={() => selectCountry(null)} />
      )}
    </div>
  );
}
