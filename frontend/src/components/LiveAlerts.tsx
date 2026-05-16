"use client";

import { formatDistanceToNow } from "date-fns";
import { Alert } from "@/lib/api";
import clsx from "clsx";

interface LiveAlertsProps {
  alerts: Alert[];
  onAcknowledge?: (id: string) => void;
}

const severityClass: Record<string, string> = {
  critical: "severity-critical",
  high: "severity-high",
  medium: "severity-medium",
  low: "severity-low",
};

export function LiveAlerts({ alerts, onAcknowledge }: LiveAlertsProps) {
  if (!alerts.length) {
    return (
      <div className="cyber-card text-center py-8 text-cyber-muted">
        No active alerts
      </div>
    );
  }

  return (
    <div className="space-y-2 max-h-96 overflow-y-auto">
      {alerts.map((alert) => (
        <div
          key={alert.id}
          className={clsx(
            "p-3 rounded-lg border flex items-start justify-between gap-3",
            severityClass[alert.severity] || severityClass.medium,
          )}
        >
          <div className="flex-1 min-w-0">
            <p className="font-medium text-white text-sm">{alert.title}</p>
            <p className="text-xs text-cyber-muted mt-1 truncate">{alert.message}</p>
            <p className="text-xs text-cyber-muted mt-1">
              {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
            </p>
          </div>
          {onAcknowledge && alert.status === "open" && (
            <button
              onClick={() => onAcknowledge(alert.id)}
              className="text-xs px-2 py-1 rounded bg-cyber-bg border border-cyber-border hover:border-cyber-accent text-cyber-muted hover:text-cyber-accent shrink-0"
            >
              ACK
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
