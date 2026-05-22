"use client";

import { useEffect, useRef } from "react";
import cytoscape, { type Core } from "cytoscape";
import type { ThreatGraphSnapshot } from "@/lib/api";

const CLUSTER_COLORS = [
  "#00ff88",
  "#ff6b6b",
  "#4dabf7",
  "#ffd43b",
  "#da77f2",
  "#ff922b",
];

interface Props {
  graph: ThreatGraphSnapshot | null;
  height?: number;
}

export function ThreatGraphCytoscape({ graph, height = 360 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!graph?.nodes?.length) {
      cyRef.current?.destroy();
      cyRef.current = null;
      return;
    }

    const elements: cytoscape.ElementDefinition[] = [];
    for (const n of graph.nodes) {
      const color =
        n.cluster_id != null
          ? CLUSTER_COLORS[n.cluster_id % CLUSTER_COLORS.length]
          : n.bot_probability > 0.6
            ? "#ff6b6b"
            : "#00ff88";
      elements.push({
        data: {
          id: n.id,
          label: n.label,
          threat: n.threat_score,
          bot: n.bot_probability,
          color,
          size: 12 + Math.min(24, n.threat_score / 4),
        },
      });
    }
    for (const e of graph.edges) {
      elements.push({
        data: {
          id: `${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          weight: e.weight,
        },
      });
    }

    cyRef.current?.destroy();
    cyRef.current = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            "font-size": 8,
            color: "#e2e8f0",
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: "data(size)",
            height: "data(size)",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "#475569",
            opacity: 0.75,
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        padding: 24,
        nodeRepulsion: 8000,
        idealEdgeLength: 80,
      },
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.2,
    });

    return () => {
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, [graph]);

  if (!graph?.nodes?.length) {
    return (
      <div
        className="flex items-center justify-center rounded-xl border border-cyber-border bg-cyber-bg/60 text-cyber-muted text-sm"
        style={{ height }}
      >
        Sin nodos en el grafo — se construye con eventos en vivo.
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="rounded-xl border border-cyber-border bg-cyber-bg/80 w-full"
      style={{ height }}
      role="img"
      aria-label="Grafo de correlación de amenazas"
    />
  );
}
