"use client";

import Link from "next/link";
import { Bell } from "lucide-react";
import type { Alert } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { LiveAlerts } from "@/components/LiveAlerts";

export function AlertsPanel({ alerts }: { alerts: Alert[] }) {
  const open = alerts.filter((a) => a.status !== "resolved").length;
  return (
    <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/50 flex flex-col min-h-[280px]">
      <div className="flex items-center justify-between p-4 border-b border-cyber-border/60">
        <div className="flex items-center gap-2">
          <Bell size={18} className="text-cyber-warning" />
          <p className="text-xs uppercase tracking-widest text-cyber-muted">Alertas live</p>
        </div>
        <Badge variant="warning">{open} abiertas</Badge>
      </div>
      <div className="p-4 flex-1">
        <LiveAlerts alerts={alerts.slice(0, 6)} />
      </div>
      <div className="px-4 pb-4">
        <Link
          href="/dashboard/alerts"
          className="text-xs text-cyber-accent hover:underline font-medium"
        >
          Centro de alertas →
        </Link>
      </div>
    </div>
  );
}
