/**
 * Alert Panel Component - Display and manage alerts with database integration
 */

"use client";

import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { AlertCircle, CheckCircle, X } from "lucide-react";
import { api } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";

type AlertSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

interface AlertPanelProps {
  streamId: string;
  refreshInterval?: number;
}

const SEVERITY_COLORS = {
  CRITICAL: "bg-red-50 border-red-300 text-red-900",
  HIGH: "bg-orange-50 border-orange-300 text-orange-900",
  MEDIUM: "bg-yellow-50 border-yellow-300 text-yellow-900",
  LOW: "bg-blue-50 border-blue-300 text-blue-900",
};

const SEVERITY_BADGE_COLORS = {
  CRITICAL: "bg-red-100 text-red-800",
  HIGH: "bg-orange-100 text-orange-800",
  MEDIUM: "bg-yellow-100 text-yellow-800",
  LOW: "bg-blue-100 text-blue-800",
};

export default function AlertPanel({ streamId, refreshInterval = 5000 }: AlertPanelProps) {
  const [showDismissed, setShowDismissed] = useState(false);
  const queryClient = useQueryClient();
  const token = useApiToken();
  const alertsQuery = useQuery({
    queryKey: ["stream-alerts", streamId],
    queryFn: async () => {
      const [activeData, dismissedData] = await Promise.all([
        api.alerts.list(token!, { status: "open", streamId }),
        api.alerts.list(token!, { status: "dismissed", streamId }),
      ]);
      return {
        active: activeData.map((alert) => ({ ...alert, severity: alert.severity.toUpperCase() as AlertSeverity })),
        dismissed: dismissedData.map((alert) => ({ ...alert, severity: alert.severity.toUpperCase() as AlertSeverity })),
      };
    },
    enabled: !!token,
    refetchInterval: refreshInterval,
  });
  const activeAlerts = alertsQuery.data?.active ?? [];
  const dismissedAlerts = alertsQuery.data?.dismissed ?? [];

  const dismissAlert = async (alertId: string) => {
    try {
      await api.alerts.dismiss(token!, alertId);
      await queryClient.invalidateQueries({ queryKey: ["stream-alerts", streamId] });
    } catch (error) {
      console.error("Dismiss error:", error);
    }
  };

  if (alertsQuery.isPending) {
    return <div className="text-gray-400">Loading alerts...</div>;
  }

  return (
    <div className="space-y-4">
      {/* Active Alerts */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
        <div className="p-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            Active Alerts ({activeAlerts.length})
          </h3>
        </div>

        {alertsQuery.error && (
          <div className="p-4 text-sm text-red-600 bg-red-50">
            {alertsQuery.error instanceof Error
              ? alertsQuery.error.message
              : "Failed to fetch alerts"}
          </div>
        )}

        <div className="divide-y divide-gray-200">
          {activeAlerts.length === 0 ? (
            <div className="p-4 text-gray-500 text-center">
              No active alerts
            </div>
          ) : (
            activeAlerts.map((alert) => (
              <div
                key={alert.id}
                className={`p-4 border-l-4 flex justify-between items-start gap-3 ${
                  SEVERITY_COLORS[alert.severity]
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-semibold">{alert.title}</h4>
                    <span
                      className={`px-2 py-0.5 text-xs font-medium rounded ${
                        SEVERITY_BADGE_COLORS[alert.severity]
                      }`}
                    >
                      {alert.severity}
                    </span>
                  </div>
                  <p className="text-sm opacity-90">{alert.message}</p>
                  <p className="text-xs opacity-75 mt-1">
                    {format(new Date(alert.created_at), "PPpp")}
                  </p>
                </div>

                <button
                  onClick={() => dismissAlert(alert.id)}
                  className="p-1 hover:bg-black hover:bg-opacity-10 rounded transition-colors flex-shrink-0"
                  title="Dismiss alert"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Dismissed Alerts */}
      {dismissedAlerts.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
          <button
            onClick={() => setShowDismissed(!showDismissed)}
            className="w-full p-4 border-b border-gray-200 flex items-center gap-2 hover:bg-gray-50 transition-colors text-left"
          >
            <CheckCircle className="w-5 h-5 text-gray-400" />
            <span className="text-sm font-medium text-gray-600">
              Dismissed Alerts ({dismissedAlerts.length})
            </span>
            <span className="ml-auto text-xs text-gray-500">
              {showDismissed ? "▾" : "▸"}
            </span>
          </button>

          {showDismissed && (
            <div className="divide-y divide-gray-100">
              {dismissedAlerts.map((alert) => (
                <div key={alert.id} className="p-4 opacity-60">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-semibold text-sm text-gray-700">
                      {alert.title}
                    </h4>
                    <span
                      className={`px-2 py-0.5 text-xs font-medium rounded ${
                        SEVERITY_BADGE_COLORS[alert.severity]
                      }`}
                    >
                      {alert.severity}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600">
                    {format(new Date(alert.created_at), "PPpp")}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
