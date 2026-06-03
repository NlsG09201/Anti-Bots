/**
 * Threat Viewer Component - Display suspicious viewers
 */

"use client";

import React, { useEffect, useState } from "react";

interface SuspiciousViewer {
  id: string;
  ip_address: string;
  username: string;
  user_id: string;
  threat_score: number;
  threat_categories: string[];
  risk_factors: string[];
  first_seen: number;
  join_count: number;
}

interface ThreatViewerProps {
  streamId: string;
  tenantId: string;
}

export default function ThreatViewer({ streamId, tenantId }: ThreatViewerProps) {
  const [viewers, setViewers] = useState<SuspiciousViewer[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"threat_score" | "join_count">("threat_score");

  useEffect(() => {
    fetchViewers();
    const interval = setInterval(fetchViewers, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, [streamId]);

  const fetchViewers = async () => {
    try {
      const response = await fetch(
        `/api/v1/threat-intelligence/stream-metrics/${streamId}?tenant_id=${tenantId}`
      );
      const data = await response.json();
      setViewers(data.viewers || []);
    } catch (error) {
      console.error("Failed to fetch viewers:", error);
    } finally {
      setLoading(false);
    }
  };

  const getThreatColor = (score: number) => {
    if (score >= 0.8) return "text-red-500";
    if (score >= 0.6) return "text-orange-500";
    if (score >= 0.4) return "text-yellow-500";
    return "text-green-500";
  };

  const getThreatBgColor = (score: number) => {
    if (score >= 0.8) return "bg-red-500 bg-opacity-10";
    if (score >= 0.6) return "bg-orange-500 bg-opacity-10";
    if (score >= 0.4) return "bg-yellow-500 bg-opacity-10";
    return "bg-green-500 bg-opacity-10";
  };

  const sortedViewers = [...viewers].sort((a, b) => {
    if (sortBy === "threat_score") {
      return b.threat_score - a.threat_score;
    } else {
      return b.join_count - a.join_count;
    }
  });

  if (loading) {
    return <div className="text-gray-400">Loading viewers...</div>;
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">
          Suspicious Viewers ({viewers.length})
        </h3>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as "threat_score" | "join_count")}
          className="bg-gray-700 text-white px-3 py-1 rounded text-sm border border-gray-600"
        >
          <option value="threat_score">Sort by Threat Score</option>
          <option value="join_count">Sort by Join Count</option>
        </select>
      </div>

      {/* Viewers Table */}
      {viewers.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-gray-400">
                <th className="text-left px-4 py-3">Username</th>
                <th className="text-left px-4 py-3">IP Address</th>
                <th className="text-left px-4 py-3">Threat Score</th>
                <th className="text-left px-4 py-3">Threat Categories</th>
                <th className="text-left px-4 py-3">Joins</th>
                <th className="text-left px-4 py-3">First Seen</th>
              </tr>
            </thead>
            <tbody>
              {sortedViewers.map((viewer) => (
                <tr key={viewer.id} className={`border-b border-gray-700 ${getThreatBgColor(viewer.threat_score)}`}>
                  <td className="px-4 py-3 font-medium">{viewer.username || "Unknown"}</td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-400">{viewer.ip_address}</td>
                  <td className={`px-4 py-3 font-semibold ${getThreatColor(viewer.threat_score)}`}>
                    {(viewer.threat_score * 100).toFixed(0)}%
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {viewer.threat_categories.slice(0, 3).map((cat) => (
                        <span key={cat} className="bg-gray-700 text-gray-300 px-2 py-1 rounded text-xs">
                          {cat}
                        </span>
                      ))}
                      {viewer.threat_categories.length > 3 && (
                        <span className="text-gray-500 text-xs px-2">
                          +{viewer.threat_categories.length - 3}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">{viewer.join_count}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {new Date(viewer.first_seen * 1000).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-8 text-gray-400">
          <p>No suspicious viewers detected</p>
        </div>
      )}

      {/* Legend */}
      <div className="pt-4 border-t border-gray-700 grid grid-cols-4 gap-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500"></div>
          <span className="text-gray-400">Critical (80-100%)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-orange-500"></div>
          <span className="text-gray-400">High (60-80%)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
          <span className="text-gray-400">Medium (40-60%)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-green-500"></div>
          <span className="text-gray-400">Low (0-40%)</span>
        </div>
      </div>
    </div>
  );
}
