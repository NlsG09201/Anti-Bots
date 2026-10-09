/**
 * Alert Panel Component - Display and manage alerts with database integration
 */

"use client";

import React, { useEffect, useState, useCallback } from "react";
import { format } from "date-fns";
import { AlertCircle, CheckCircle, X } from "lucide-react";

interface Alert {
  id: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  title: string;
  description: string;
  created_at: string;
  stream_id: string;
  dismissed: boolean;
  type: string;
  data?: Record<string, any>;
}

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
  const [activeAlerts, setActiveAlerts] = useState<Alert[]>([]);
  const [dismissedAlerts, setDismissedAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDismissed, setShowDismissed] = useState(false);

  const fetchAlerts = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch active alerts
      const activeResponse = await fetch(
        `/api/v1/alerts/stream/${streamId}/active?limit=20`
      );
      if (!activeResponse.ok) {
        throw new Error("Failed to fetch active alerts");
      }
      const activeData = await activeResponse.json();

      // Fetch dismissed alerts
      const dismissedResponse = await fetch(
        `/api/v1/alerts/${streamId}?dismissed=true&limit=10`
      );
      if (!dismissedResponse.ok) {
        throw new Error("Failed to fetch dismissed alerts");
      }
      const dismissedData = await dismissedResponse.json();

      setActiveAlerts(activeData.items || []);
      setDismissedAlerts(dismissedData.items || []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch alerts"
      );
      console.error("Alert fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, [streamId]);

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, refreshInterval);
    return () => clearInterval(interval);
  }, [streamId, refreshInterval, fetchAlerts]);

  const dismissAlert = async (alertId: string) => {
    try {
      const response = await fetch(`/api/v1/alerts/${alertId}/dismiss`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Dismissed by user" }),
      });
      if (!response.ok) {
        throw new Error("Failed to dismiss alert");
      }
      setActiveAlerts(activeAlerts.filter((a) => a.id !== alertId));
      await fetchAlerts();
    } catch (error) {
      console.error("Dismiss error:", error);
    }
  };

  if (loading) {
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

        {error && (
          <div className="p-4 text-sm text-red-600 bg-red-50">
            {error}
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
                  <p className="text-sm opacity-90">{alert.description}</p>
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
