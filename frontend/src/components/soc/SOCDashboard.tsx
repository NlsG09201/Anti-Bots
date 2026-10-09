/**
 * SOC Dashboard - Main threat intelligence dashboard component
 */

"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useWebSocket, type WSMessage } from "@/hooks/useWebSocket";
import ThreatViewer from "./ThreatViewer";
import ThreatMetrics from "./ThreatMetrics";
import AttackTimeline from "./AttackTimeline";
import AlertPanel from "./AlertPanel";
import ThreatMap from "./ThreatMap";
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";

interface StreamThreatData {
  stream_id: string;
  overall_risk_score: number;
  viewer_count: number;
  detected_attacks: string[];
  threat_components: {
    ip_threats: {
      threat_score: number;
      suspicious_ips: number;
      threat_categories: string[];
    };
    behavioral: {
      behavioral_threat_score: number;
      patterns_detected: string[];
      patterns_detail: Record<string, { detected: boolean; confidence: number }>;
    };
    chat: {
      chat_threat_score: number;
      spam_indicators: number;
      coordinated_spam_detected: boolean;
    };
    graph_correlation?: {
      graph_threat_score: number;
      detected_clusters: number;
      coordination_score: number;
    };
  };
}

export interface SOCDashboardProps {
  streamId: string;
  tenantId: string;
}

export default function SOCDashboard({ streamId, tenantId }: SOCDashboardProps) {
  const [threatData, setThreatData] = useState<StreamThreatData | null>(null);
  const [riskHistory, setRiskHistory] = useState<Array<{ timestamp: number; risk: number }>>([]);
  const [selectedTab, setSelectedTab] = useState<"overview" | "viewers" | "timeline" | "alerts">("overview");

  // The current application uses the shared authenticated WebSocket (/ws/live).
  // This legacy component only accepts messages that contain its complete payload.
  const onWsMessage = useCallback((message: WSMessage) => {
    if (message.type !== "stream_threat_update" || !message.data) return;
    const payload = message.data as unknown as StreamThreatData;
    if (payload.stream_id !== streamId || typeof payload.overall_risk_score !== "number") return;
    setThreatData(payload);
    setRiskHistory((prev) => [
      ...prev.slice(-59),
      { timestamp: Date.now(), risk: payload.overall_risk_score * 100 },
    ]);
  }, [streamId]);
  const { connected: isConnected } = useWebSocket(onWsMessage);

  // Determine threat level color
  const getThreatColor = (score: number) => {
    if (score >= 0.8) return "text-red-600";
    if (score >= 0.6) return "text-orange-600";
    if (score >= 0.4) return "text-yellow-600";
    return "text-green-600";
  };

  // Determine threat level label
  const getThreatLevel = (score: number) => {
    if (score >= 0.8) return "CRITICAL";
    if (score >= 0.6) return "HIGH";
    if (score >= 0.4) return "MEDIUM";
    return "LOW";
  };

  if (!threatData) {
    return (
      <div className="flex items-center justify-center w-full h-96">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mb-4"></div>
          <p className="text-gray-600">Loading threat assessment...</p>
        </div>
      </div>
    );
  }

  const riskScore = threatData.overall_risk_score;
  const threatLevel = getThreatLevel(riskScore);
  const threatColor = getThreatColor(riskScore);

  return (
    <div className="w-full h-full bg-gray-900 text-white p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-4xl font-bold mb-2">Threat Intelligence SOC</h1>
            <p className="text-gray-400">Stream ID: {streamId}</p>
          </div>
          
          {/* Connection Status */}
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${isConnected ? "bg-green-500 animate-pulse" : "bg-red-500"}`}></div>
            <span className="text-sm">{isConnected ? "Live" : "Reconnecting..."}</span>
          </div>
        </div>

        {/* Main Risk Indicator */}
        <div className={`inline-block p-6 rounded-lg bg-gradient-to-r from-gray-800 to-gray-700 border-2 ${threatColor} border-opacity-30`}>
          <div className="text-sm text-gray-400 mb-2">Overall Threat Level</div>
          <div className={`text-5xl font-bold ${threatColor} mb-2`}>{threatLevel}</div>
          <div className="text-2xl font-semibold text-gray-300">{(riskScore * 100).toFixed(1)}% Risk</div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-gray-400 text-sm mb-2">Viewers</div>
          <div className="text-3xl font-bold">{threatData.viewer_count}</div>
          <div className={`text-sm mt-2 ${threatData.threat_components.ip_threats.suspicious_ips > 0 ? "text-orange-400" : "text-green-400"}`}>
            {threatData.threat_components.ip_threats.suspicious_ips} suspicious
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-gray-400 text-sm mb-2">IP Threat Score</div>
          <div className="text-3xl font-bold">
            {(threatData.threat_components.ip_threats.threat_score * 100).toFixed(0)}%
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-gray-400 text-sm mb-2">Behavioral Anomalies</div>
          <div className="text-3xl font-bold">
            {(threatData.threat_components.behavioral.behavioral_threat_score * 100).toFixed(0)}%
          </div>
          <div className="text-xs mt-2 text-gray-400">
            {threatData.threat_components.behavioral.patterns_detected.length} patterns
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-gray-400 text-sm mb-2">Chat Threat Score</div>
          <div className="text-3xl font-bold">
            {(threatData.threat_components.chat.chat_threat_score * 100).toFixed(0)}%
          </div>
          <div className="text-xs mt-2 text-gray-400">
            {threatData.threat_components.chat.spam_indicators} spam indicators
          </div>
        </div>
      </div>

      {/* Active Attacks */}
      {threatData.detected_attacks.length > 0 && (
        <div className="mb-8 bg-red-900 bg-opacity-30 border border-red-500 border-opacity-30 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
            <h3 className="text-lg font-semibold text-red-400">Active Attacks Detected</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {threatData.detected_attacks.map((attack) => (
              <span key={attack} className="bg-red-500 bg-opacity-20 text-red-400 px-3 py-1 rounded text-sm font-medium">
                {attack}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Risk Over Time Chart */}
      {riskHistory.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-6 mb-8">
          <h2 className="text-xl font-semibold mb-4">Threat Level Timeline</h2>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={riskHistory}>
              <defs>
                <linearGradient id="threatGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.1} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="timestamp" hide />
              <YAxis stroke="#9ca3af" domain={[0, 100]} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                formatter={(value) => `${(value as number).toFixed(1)}%`}
              />
              <Area type="monotone" dataKey="risk" stroke="#ef4444" fill="url(#threatGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-4 mb-6 border-b border-gray-700">
        {(["overview", "viewers", "timeline", "alerts"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setSelectedTab(tab)}
            className={`px-4 py-2 font-medium transition-colors ${
              selectedTab === tab
                ? "text-blue-400 border-b-2 border-blue-400"
                : "text-gray-400 hover:text-gray-300"
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="bg-gray-800 rounded-lg p-6">
        {selectedTab === "overview" && <ThreatMetrics threatData={threatData} />}
        {selectedTab === "viewers" && <ThreatViewer streamId={streamId} tenantId={tenantId} />}
        {selectedTab === "timeline" && <AttackTimeline streamId={streamId} />}
        {selectedTab === "alerts" && <AlertPanel streamId={streamId} />}
      </div>
    </div>
  );
}
