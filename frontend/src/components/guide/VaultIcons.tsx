"use client";
import React from "react";
import type { SVGProps } from "react";

// All icons use fill="currentColor" — styled via parent element color/glow.
// viewBox 40×48, Vault Boy silhouette aesthetic.

type P = SVGProps<SVGSVGElement>;

function Svg({ children, viewBox = "0 0 40 48", ...p }: { children: React.ReactNode } & P) {
  return (
    <svg viewBox={viewBox} fill="currentColor" xmlns="http://www.w3.org/2000/svg" {...p}>
      {children}
    </svg>
  );
}

// ── Shared base: head + neck + torso ─────────────────────
const Head = ({ cx = 20, cy = 9 }: { cx?: number; cy?: number }) => (
  <>
    <ellipse cx={cx} cy={cy} rx="8" ry="8.5" />
    <circle cx={cx - 2.8} cy={cy - 1} r="1.5" fill="var(--bg)" />
    <circle cx={cx + 2.8} cy={cy - 1} r="1.5" fill="var(--bg)" />
    <path
      d={`M${cx - 3} ${cy + 3} Q${cx} ${cy + 5.5} ${cx + 3} ${cy + 3}`}
      fill="none" stroke="var(--bg)" strokeWidth="1.2" strokeLinecap="round"
    />
  </>
);
const Neck = ({ x = 18, y = 17 }: { x?: number; y?: number }) => <rect x={x} y={y} width="4" height="2.5" />;
const Body = ({ cx = 20, cy = 30 }: { cx?: number; cy?: number }) => <ellipse cx={cx} cy={cy} rx="7.5" ry="9" />;

// ── WATER — swimming, arms out, waves ────────────────────
export function WaterIcon(p: P) {
  return (
    <Svg {...p}>
      <Head />
      <Neck />
      <ellipse cx="20" cy="27" rx="6.5" ry="7.5" />
      {/* arms spread */}
      <ellipse cx="7" cy="23" rx="6" ry="3" transform="rotate(-15 7 23)" />
      <ellipse cx="33" cy="23" rx="6" ry="3" transform="rotate(15 33 23)" />
      {/* water waves */}
      <path d="M0 37 Q5 32 10 37 Q15 42 20 37 Q25 32 30 37 Q35 42 40 37 L40 48 L0 48Z" />
    </Svg>
  );
}

// ── FOOD — holding a ration can, thumbs up ────────────────
export function FoodIcon(p: P) {
  return (
    <Svg {...p}>
      <Head cx={14} />
      <Neck x={12} />
      <Body cx={14} cy={28} />
      {/* left arm raised thumbs up */}
      <path d="M8 24 L5 16 C5 12 10 12 10 16 L10 24Z" />
      {/* can body */}
      <rect x="22" y="11" width="14" height="18" rx="2.5" />
      <rect x="21" y="9.5" width="16" height="3.5" rx="1.5" />
      <rect x="21" y="25.5" width="16" height="3.5" rx="1.5" />
      {/* label lines cutout */}
      <rect x="25" y="16" width="8" height="1.8" rx="0.9" fill="var(--bg)" />
      <rect x="25" y="20" width="5" height="1.8" rx="0.9" fill="var(--bg)" />
    </Svg>
  );
}

// ── SHELTER — vault door circular hatch ──────────────────
export function ShelterIcon(p: P) {
  return (
    <Svg viewBox="0 0 44 44" {...p}>
      {/* outer ring */}
      <path
        fillRule="evenodd"
        d="M22 0 A22 22 0 1 0 22 44 A22 22 0 1 0 22 0 Z M22 8 A14 14 0 1 1 22 36 A14 14 0 1 1 22 8 Z"
      />
      {/* 8 gear teeth */}
      {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
        <rect
          key={a}
          x="19.5" y="0"
          width="5" height="5"
          rx="1"
          transform={`rotate(${a} 22 22)`}
        />
      ))}
      {/* cross handle */}
      <rect x="13" y="20.5" width="18" height="3" rx="1.5" />
      <rect x="20.5" y="13" width="3" height="18" rx="1.5" />
      {/* center hub */}
      <circle cx="22" cy="22" r="4.5" />
    </Svg>
  );
}

// ── HEALTH — body shaped as first-aid cross ───────────────
export function HealthIcon(p: P) {
  return (
    <Svg {...p}>
      <Head />
      <Neck />
      {/* cross body */}
      <rect x="15" y="18" width="10" height="28" rx="2" />
      <rect x="8" y="25" width="24" height="10" rx="2" />
    </Svg>
  );
}

// ── COMMUNICATION — walkie-talkie + signal waves ──────────
export function CommunicationIcon(p: P) {
  return (
    <Svg {...p}>
      <Head cx={14} />
      {/* antenna */}
      <rect x="17" y="-1" width="2.5" height="9" rx="1.2" />
      <circle cx="18.3" cy="-1" r="2" />
      <Neck x={12} />
      <Body cx={14} cy={29} />
      {/* walkie-talkie */}
      <rect x="23" y="14" width="13" height="20" rx="2" />
      <rect x="27" y="9" width="5" height="7" rx="2.5" />
      <rect x="25" y="17" width="9" height="6" rx="1" fill="var(--bg)" />
      {/* signal arcs */}
      <path d="M38 24 Q41.5 20 38 16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M40 27 Q44.5 20 40 13" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </Svg>
  );
}

// ── EVACUATION — running figure + arrow ──────────────────
export function EvacuationIcon(p: P) {
  return (
    <Svg {...p}>
      {/* arrow up-right */}
      <path d="M3 16 L3 4 L15 4" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3 4 L15 16" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
      {/* running vault boy */}
      <ellipse cx="28" cy="9" rx="7" ry="7.5" />
      <ellipse cx="24" cy="24" rx="6" ry="8" transform="rotate(18 24 24)" />
      {/* legs running */}
      <ellipse cx="19" cy="38" rx="4.5" ry="8" transform="rotate(-25 19 38)" />
      <ellipse cx="30" cy="36" rx="4.5" ry="8" transform="rotate(30 30 36)" />
      {/* arms */}
      <ellipse cx="16" cy="22" rx="3.5" ry="7" transform="rotate(40 16 22)" />
      <ellipse cx="31" cy="20" rx="3.5" ry="7" transform="rotate(-30 31 20)" />
    </Svg>
  );
}

// ── ENERGY — lightning bolt in raised hand ────────────────
export function EnergyIcon(p: P) {
  return (
    <Svg {...p}>
      <Head cx={13} />
      <Neck x={11} />
      <Body cx={13} cy={29} />
      {/* arm raised */}
      <ellipse cx="8" cy="22" rx="3.5" ry="7" transform="rotate(-30 8 22)" />
      {/* lightning bolt */}
      <path d="M22 2 L15 22 L22 22 L14 46 L32 18 L25 18Z" />
    </Svg>
  );
}

// ── SECURITY — vault boy behind shield ───────────────────
export function SecurityIcon(p: P) {
  return (
    <Svg {...p}>
      <Head />
      <Neck />
      {/* shield covers body */}
      <path d="M5 18 L35 18 L35 36 Q20 48 5 36 Z" />
      {/* shield window cutout */}
      <path d="M11 23 L29 23 L29 34 Q20 40 11 34 Z" fill="var(--bg)" />
      {/* vault boy torso showing inside shield */}
      <ellipse cx="20" cy="31" rx="5.5" ry="7" />
    </Svg>
  );
}

// ── DOCUMENTATION — clipboard with lines ─────────────────
export function DocumentationIcon(p: P) {
  return (
    <Svg {...p}>
      <Head />
      <Neck />
      {/* clipboard body */}
      <rect x="8" y="17" width="24" height="30" rx="2.5" />
      {/* clip at top */}
      <rect x="14" y="14" width="12" height="6" rx="2" />
      <rect x="17" y="12" width="6" height="5" rx="2" fill="var(--bg)" />
      {/* text lines */}
      <rect x="12" y="24" width="16" height="2" rx="1" fill="var(--bg)" />
      <rect x="12" y="29" width="16" height="2" rx="1" fill="var(--bg)" />
      <rect x="12" y="34" width="10" height="2" rx="1" fill="var(--bg)" />
      <rect x="12" y="39" width="13" height="2" rx="1" fill="var(--bg)" />
    </Svg>
  );
}

// ── MENTAL HEALTH — seated, peaceful, stars ───────────────
export function MentalHealthIcon(p: P) {
  return (
    <Svg {...p}>
      <Head />
      <Neck />
      {/* sitting torso */}
      <ellipse cx="20" cy="28" rx="7" ry="7.5" />
      {/* crossed legs */}
      <ellipse cx="11" cy="38" rx="8.5" ry="5" transform="rotate(15 11 38)" />
      <ellipse cx="29" cy="38" rx="8.5" ry="5" transform="rotate(-15 29 38)" />
      {/* arms raised — peaceful */}
      <ellipse cx="8" cy="24" rx="3.5" ry="6.5" transform="rotate(-40 8 24)" />
      <ellipse cx="32" cy="24" rx="3.5" ry="6.5" transform="rotate(40 32 24)" />
      {/* stars */}
      <path d="M20 -1 L21 2 L24 2 L22 4 L23 7 L20 5 L17 7 L18 4 L16 2 L19 2Z" />
    </Svg>
  );
}

// ── ARMED CONFLICT — radiation trefoil ───────────────────
export function ArmedConflictIcon(p: P) {
  return (
    <Svg viewBox="0 0 44 44" {...p}>
      {/* outer border ring */}
      <path
        fillRule="evenodd"
        d="M22 1 A21 21 0 1 0 22 43 A21 21 0 1 0 22 1 Z M22 4 A18 18 0 1 1 22 40 A18 18 0 1 1 22 4 Z"
      />
      {/* center circle */}
      <circle cx="22" cy="22" r="5" />
      {/* trefoil sectors — 3 × 60° fans, r=7 to R=16, separated by 60° gaps */}
      {/* sector top (240°–300°) */}
      <path d="M22 22 L15.0 9.88 A14 14 0 0 1 29.0 9.88 L25.46 18 A5 5 0 0 0 18.54 18 Z" />
      {/* sector bottom-right (0°–60°) */}
      <path d="M22 22 L36 22 A14 14 0 0 1 29.0 34.12 L24 26.5 A5 5 0 0 0 26.5 22 Z" />
      {/* sector bottom-left (120°–180°) */}
      <path d="M22 22 L8 22 A14 14 0 0 0 15 34.12 L18 26.5 A5 5 0 0 1 17.5 22 Z" />
    </Svg>
  );
}

// ── FAMILY — adult + child vault boys ────────────────────
export function FamilyIcon(p: P) {
  return (
    <Svg {...p}>
      {/* adult left */}
      <ellipse cx="13" cy="9" rx="7" ry="7.5" />
      <circle cx="10.2" cy="8" r="1.3" fill="var(--bg)" />
      <circle cx="15.8" cy="8" r="1.3" fill="var(--bg)" />
      <rect x="11" y="16" width="4" height="2.5" />
      <ellipse cx="13" cy="28" rx="6.5" ry="8.5" />
      {/* adult arm around child */}
      <path d="M19 20 Q26 17 28 22 L25 23 Q23 18 19 22Z" />

      {/* child right — smaller */}
      <ellipse cx="29" cy="16" rx="5.5" ry="6" />
      <circle cx="27" cy="15" r="1.1" fill="var(--bg)" />
      <circle cx="31" cy="15" r="1.1" fill="var(--bg)" />
      <rect x="27" y="22" width="4" height="2" />
      <ellipse cx="29" cy="32" rx="5.5" ry="7" />
    </Svg>
  );
}

// ── Map by category id ────────────────────────────────────
const ICON_MAP: Record<string, (p: P) => React.ReactElement | null> = {
  water:               WaterIcon,
  food:                FoodIcon,
  shelter:             ShelterIcon,
  health:              HealthIcon,
  communication:       CommunicationIcon,
  evacuation:          EvacuationIcon,
  energy:              EnergyIcon,
  security:            SecurityIcon,
  documentation:       DocumentationIcon,
  mental_health:       MentalHealthIcon,
  armed_conflict:      ArmedConflictIcon,
  family_coordination: FamilyIcon,
};

export function VaultIcon({ id, ...p }: { id: string } & P) {
  const Comp = ICON_MAP[id];
  return Comp ? <Comp {...p} /> : null;
}
