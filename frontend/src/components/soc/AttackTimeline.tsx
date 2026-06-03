/**
 * Attack Timeline Component - Show threat events over time
 */

"use client";

import React, { useEffect, useState } from "react";
import { format } from "date-fns";

interface TimelineEvent {
  id: string;
  timestamp: number;
  event_type: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  title: string;
  description: string;
  viewer_count: number;
  threat_score: number;
}

interface AttackTimelineProps {
  streamId: string;
}

const SEVERITY_ICON = {
  CRITICAL: "🔴",
  HIGH: "🟠",
  MEDIUM: "🟡",
  LOW: "🔵",
};

export default function AttackTimeline({ streamId }: AttackTimelineProps) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTimeline();
    const interval = setInterval(fetchTimeline, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, [streamId]);

  const fetchTimeline = async () => {
    try {
      const response = await fetch(
        `/api/v1/threat-intelligence/threat-timeline/${streamId}?limit=100`
      );
      const data = await response.json();
      setEvents(data.events || []);
    } catch (error) {
      console.error("Failed to fetch timeline:", error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-gray-400">Loading timeline...</div>;
  }

  if (events.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <p>No threat events recorded</p>
        <p className="text-sm text-gray-500 mt-2">Events will appear as they are detected</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {/* Timeline */}
      <div className="relative">
        {events.map((event, index) => (
          <div key={event.id} className="flex gap-4 pb-6 relative">
            {/* Timeline line */}
            {index !== events.length - 1 && (
              <div className="absolute left-5 top-12 w-0.5 h-12 bg-gradient-to-b from-gray-600 to-gray-700"></div>
            )}

            {/* Timeline dot */}
            <div className="relative pt-1">
              <div className={`w-12 h-12 rounded-full border-4 flex items-center justify-center text-lg
                ${event.severity === "CRITICAL" ? "bg-red-500 border-red-600" :
                  event.severity === "HIGH" ? "bg-orange-500 border-orange-600" :
                  event.severity === "MEDIUM" ? "bg-yellow-500 border-yellow-600" :
                  "bg-blue-500 border-blue-600"}`}>
                {SEVERITY_ICON[event.severity]}
              </div>
            </div>

            {/* Event content */}
            <div className="flex-1 pt-2">
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h4 className="font-semibold text-white">{event.title}</h4>
                    <p className="text-sm text-gray-400 mt-1">{event.description}</p>
                  </div>
                  <span className={`px-3 py-1 rounded text-xs font-semibold whitespace-nowrap ml-2
                    ${event.severity === "CRITICAL" ? "bg-red-500 text-white" :
                      event.severity === "HIGH" ? "bg-orange-500 text-white" :
                      event.severity === "MEDIUM" ? "bg-yellow-500 text-black" :
                      "bg-blue-500 text-white"}`}>
                    {event.severity}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-4 mt-3 pt-3 border-t border-gray-700">
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Time</div>
                    <div className="text-sm font-mono text-gray-300">
                      {format(new Date(event.timestamp * 1000), "HH:mm:ss")}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Viewers at Event</div>
                    <div className="text-sm font-semibold text-white">{event.viewer_count}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Threat Score</div>
                    <div className={`text-sm font-semibold
                      ${event.threat_score >= 0.8 ? "text-red-400" :
                        event.threat_score >= 0.6 ? "text-orange-400" :
                        event.threat_score >= 0.4 ? "text-yellow-400" :
                        "text-green-400"}`}>
                      {(event.threat_score * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Statistics */}
      <div className="mt-8 pt-6 border-t border-gray-700 grid grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-red-400">
            {events.filter((e) => e.severity === "CRITICAL").length}
          </div>
          <div className="text-sm text-gray-400 mt-1">Critical Events</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-orange-400">
            {events.filter((e) => e.severity === "HIGH").length}
          </div>
          <div className="text-sm text-gray-400 mt-1">High Events</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-yellow-400">
            {events.filter((e) => e.severity === "MEDIUM").length}
          </div>
          <div className="text-sm text-gray-400 mt-1">Medium Events</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-blue-400">{events.length}</div>
          <div className="text-sm text-gray-400 mt-1">Total Events</div>
        </div>
      </div>
    </div>
  );
}
