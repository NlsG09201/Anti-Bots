"use client";

import Link from "next/link";
import { Bot, ExternalLink } from "lucide-react";
import type { Stream, Viewer } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SuspiciousViewersProps {
  viewers: Viewer[];
  stream?: Stream | null;
}

export function SuspiciousViewers({ viewers, stream }: SuspiciousViewersProps) {
  return (
    <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/50 flex flex-col h-full min-h-[320px]">
      <div className="flex items-center justify-between p-4 border-b border-cyber-border/60">
        <div>
          <p className="text-xs uppercase tracking-widest text-cyber-muted">Viewers sospechosos</p>
          <p className="text-sm text-white font-medium mt-0.5">
            {stream ? stream.channel_name : "Sin canal live"}
          </p>
        </div>
        <Badge variant="danger">{viewers.length} flagged</Badge>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1 max-h-[360px]">
        {viewers.length ? (
          viewers.slice(0, 12).map((v) => (
            <div
              key={v.id}
              className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-cyber-bg/60 border border-transparent hover:border-cyber-border/50 transition-colors"
            >
              <div className="p-2 rounded-lg bg-cyber-danger/10 text-cyber-danger">
                <Bot size={16} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-white truncate">{v.platform_username}</p>
                <p className="text-[10px] font-mono text-cyber-muted truncate">
                  {v.ip_address || "—"} · risk {v.risk_score.toFixed(0)}
                </p>
              </div>
              <span
                className={cn(
                  "text-xs font-mono font-semibold",
                  v.risk_score >= 70 ? "text-cyber-danger" : "text-cyber-warning",
                )}
              >
                {v.risk_score.toFixed(0)}
              </span>
            </div>
          ))
        ) : (
          <p className="text-sm text-cyber-muted text-center py-12 px-4">
            No hay viewers marcados como sospechosos en este canal.
          </p>
        )}
      </div>
      <div className="p-3 border-t border-cyber-border/60">
        <Link href="/dashboard/viewers">
          <Button variant="outline" size="sm" className="w-full">
            Ver todos
            <ExternalLink size={14} />
          </Button>
        </Link>
      </div>
    </div>
  );
}
