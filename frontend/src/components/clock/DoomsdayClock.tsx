"use client";
import { useMemo } from "react";

interface Props {
  secondsToMidnight: number;
  riskLevel: "green" | "yellow" | "orange" | "red";
  size?: number;
}

const RISK_COLORS = { green: "#22c55e", yellow: "#eab308", orange: "#f97316", red: "#ef4444" };

export default function DoomsdayClock({ secondsToMidnight, riskLevel, size = 200 }: Props) {
  const color = RISK_COLORS[riskLevel];
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.45;

  const angle = useMemo(() => {
    const windowSeconds = 300;
    const clamped = Math.min(secondsToMidnight, windowSeconds);
    const progress = 1 - clamped / windowSeconds;
    return -120 + progress * 30;
  }, [secondsToMidnight]);

  const handLength = r * 0.78;
  const handX = cx + handLength * Math.cos((angle * Math.PI) / 180);
  const handY = cy + handLength * Math.sin((angle * Math.PI) / 180);

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
        className={riskLevel === "red" ? "risk-red-pulse rounded-full" : ""}>
        <circle cx={cx} cy={cy} r={r} fill="#111" stroke={color} strokeWidth="2" />
        {Array.from({ length: 60 }).map((_, i) => {
          const a = (i / 60) * 2 * Math.PI - Math.PI / 2;
          const inner = i % 5 === 0 ? r - 14 : r - 8;
          return (
            <line key={i}
              x1={cx + inner * Math.cos(a)} y1={cy + inner * Math.sin(a)}
              x2={cx + (r - 3) * Math.cos(a)} y2={cy + (r - 3) * Math.sin(a)}
              stroke={i % 5 === 0 ? color : "#333"} strokeWidth={i % 5 === 0 ? 2 : 1} />
          );
        })}
        <line x1={cx} y1={cy} x2={handX} y2={handY}
          stroke={color} strokeWidth="3" strokeLinecap="round" className="clock-hand" />
        <circle cx={cx} cy={cy} r={4} fill={color} />
      </svg>
      <div className="text-center">
        <div className="font-mono text-3xl font-bold tracking-tight" style={{ color }}>
          {Math.round(secondsToMidnight)}
          <span className="text-lg font-normal ml-1">seconds</span>
        </div>
        <div className="text-xs text-gray-500 uppercase tracking-widest mt-0.5">to midnight</div>
      </div>
    </div>
  );
}
