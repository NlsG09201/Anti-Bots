"use client";

import { useMemo } from "react";
import type { MapThreat } from "@/hooks/useSocData";
import { projectLatLng } from "@/lib/country-coords";
import { cn } from "@/lib/utils";

interface AttackMapProps {
  threats: MapThreat[];
  className?: string;
}

const W = 720;
const H = 360;

export function AttackMap({ threats, className }: AttackMapProps) {
  const dots = useMemo(
    () =>
      threats.map((t) => ({
        ...t,
        ...projectLatLng(t.lat, t.lng, W, H),
      })),
    [threats],
  );

  return (
    <div className={cn("relative overflow-hidden rounded-lg", className)}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-[280px] md:h-[320px]"
        role="img"
        aria-label="Mapa global de amenazas"
      >
        <defs>
          <radialGradient id="mapGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#00ff88" stopOpacity="0.08" />
            <stop offset="100%" stopColor="#060a12" stopOpacity="0" />
          </radialGradient>
          <filter id="dotGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect width={W} height={H} fill="url(#mapGlow)" />
        {/* Grid */}
        {Array.from({ length: 13 }).map((_, i) => (
          <line
            key={`v${i}`}
            x1={(i / 12) * W}
            y1={0}
            x2={(i / 12) * W}
            y2={H}
            stroke="#1e293b"
            strokeWidth={0.5}
            opacity={0.5}
          />
        ))}
        {Array.from({ length: 7 }).map((_, i) => (
          <line
            key={`h${i}`}
            x1={0}
            y1={(i / 6) * H}
            x2={W}
            y2={(i / 6) * H}
            stroke="#1e293b"
            strokeWidth={0.5}
            opacity={0.5}
          />
        ))}
        {/* Simplified continents outline */}
        <path
          d="M120 80 Q180 60 240 90 T360 70 Q420 100 480 85 T600 95 L620 120 Q580 160 520 150 T400 170 Q320 190 280 175 T180 200 Q140 180 120 150 Z"
          fill="#151b24"
          stroke="#334155"
          strokeWidth={1}
          opacity={0.9}
        />
        <path
          d="M80 200 Q140 180 200 210 T320 195 Q380 220 450 205 T560 230 L540 280 Q480 300 400 285 T280 310 Q200 320 150 300 T90 260 Z"
          fill="#151b24"
          stroke="#334155"
          strokeWidth={1}
          opacity={0.85}
        />
        {dots.map((d) => {
          const r = 4 + Math.min(d.risk / 25, 8);
          const color = d.risk >= 75 ? "#ff3366" : d.risk >= 50 ? "#ffaa00" : "#00ff88";
          return (
            <g key={d.id} filter="url(#dotGlow)">
              <circle cx={d.x} cy={d.y} r={r + 6} fill={color} opacity={0.15} />
              <circle cx={d.x} cy={d.y} r={r} fill={color} opacity={0.9}>
                <animate
                  attributeName="opacity"
                  values="0.6;1;0.6"
                  dur="2s"
                  repeatCount="indefinite"
                />
              </circle>
            </g>
          );
        })}
      </svg>
      <div className="absolute bottom-3 left-3 flex gap-3 text-[10px] font-mono text-cyber-muted">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-cyber-accent" /> Low
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-cyber-warning" /> Med
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-cyber-danger" /> High
        </span>
      </div>
      <p className="absolute top-3 right-3 text-xs text-cyber-muted font-mono">
        {dots.length} nodos activos
      </p>
    </div>
  );
}
