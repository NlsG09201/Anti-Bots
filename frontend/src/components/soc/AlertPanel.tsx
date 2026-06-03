/**
 * Alert Panel Component - Display and manage alerts
 */

"use client";

import React, { useEffect, useState } from "react";
import { format } from "date-fns";

interface Alert {
  id: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  title: string;
  description: string;
  timestamp: number;
  stream_id: string;
  dismissed: boolean;
}

interface AlertPanelProps {
  streamId: string;
}

const SEVERITY_COLORS = {
  CRITICAL: "bg-red-500 text-white",
  HIGH: "bg-orange-500 text-white",
  MEDIUM: "bg-yellow-500 text-black",
  LOW: "bg-blue-500 text-white",
};

const SEVERITY_BORDER = {
  CRITICAL: "border-red-500",
  HIGH: "border-orange-500",
  MEDIUM: "border-yellow-500",
  LOW: "border-blue-500",
};

export default function AlertPanel({ streamId }: AlertPanelProps) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, [streamId]);

  const fetchAlerts = async () => {
    try {
      const response = await fetch(`/api/v1/threat-intelligence/alerts/${streamId}?limit=50`);
      const data = await response.json();
      setAlerts(data.alerts || []);
    } catch (error) {
      console.error("Failed to fetch alerts:", error);
    } finally {
      setLoading(false);
    }
  };

  const dismissAlert = async (alertId: string) => {
    try {
      await fetch("/api/v1/threat-intelligence/alerts/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert_id: alertId }),
      });
      fetchAlerts(); // Refresh alerts
    } catch (error) {
      console.error("Failed to dismiss alert:", error);
    }
  };

  const activeAlerts = alerts.filter((a) => !a.dismissed);
  const dismissedAlerts = alerts.filter((a) => a.dismissed);

  if (loading) {
    return <div className="text-gray-400">Loading alerts...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Active Alerts */}
      {activeAlerts.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-4 text-red-400">
            Active Alerts ({activeAlerts.length})
          </h3>
          <div className="space-y-3">
            {activeAlerts.map((alert) => (
              <div
                key={alert.id}
                className={`border-l-4 p-4 rounded bg-gray-800 ${SEVERITY_BORDER[alert.severity]}`}
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-3">
                    <span className={`px-3 py-1 rounded text-sm font-semibold ${SEVERITY_COLORS[alert.severity]}`}>
                      {alert.severity}
                    </span>
                    <h4 className="font-semibold text-white">{alert.title}</h4>
                  </div>
                  <button
                    onClick={() => dismissAlert(alert.id)}
                    className="text-gray-400 hover:text-white transition-colors text-sm"
                  >
                    Dismiss
                  </button>
                </div>
                <p className="text-gray-300 mb-2">{alert.description}</p>
                <p className="text-xs text-gray-500">
                  {format(new Date(alert.timestamp * 1000), "PPpp")}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* No Active Alerts */}
      {activeAlerts.length === 0 && dismissedAlerts.length === 0 && (
        <div className="text-center py-12">
          <div className="text-4xl mb-3">✅</div>
          <p className="text-gray-400">No alerts detected</p>
          <p className="text-gray-500 text-sm">Stream is operating normally</p>
        </div>
      )}

      {/* Dismissed Alerts */}
      {dismissedAlerts.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-4 text-gray-400">
            Dismissed Alerts ({dismissedAlerts.length})
          </h3>
          <div className="space-y-2 opacity-60">
            {dismissedAlerts.slice(0, 5).map((alert) => (
              <div key={alert.id} className="p-3 rounded bg-gray-800 text-sm text-gray-400">
                <span className={`px-2 py-1 rounded text-xs font-semibold mr-2 ${SEVERITY_COLORS[alert.severity]}`}>
                  {alert.severity}
                </span>
                {alert.title}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
