/**
 * Threat Metrics Component - Detailed threat analysis display
 */

"use client";

import React from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";

interface ThreatMetricsProps {
  threatData: {
    threat_components: {
      ip_threats: {
        threat_score: number;
        suspicious_ips: number;
        threat_categories: string[];
      };
      behavioral: {
        behavioral_threat_score: number;
        patterns_detected: string[];
        patterns_detail: {
          [key: string]: {
            detected: boolean;
            confidence: number;
          };
        };
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
    viewer_count: number;
  };
}

export default function ThreatMetrics({ threatData }: ThreatMetricsProps) {
  const { threat_components } = threatData;

  // Threat score distribution data
  const threatScoreData = [
    {
      name: "IP Threats",
      value: Math.round(threat_components.ip_threats.threat_score * 100),
    },
    {
      name: "Behavioral",
      value: Math.round(threat_components.behavioral.behavioral_threat_score * 100),
    },
    {
      name: "Chat",
      value: Math.round(threat_components.chat.chat_threat_score * 100),
    },
    {
      name: "Graph",
      value: Math.round((threat_components.graph_correlation?.graph_threat_score || 0) * 100),
    },
  ];

  const COLORS = ["#ef4444", "#f97316", "#eab308", "#84cc16"];

  // Detected patterns with confidence
  const patterns = threat_components.behavioral.patterns_detail || {};
  const patternData = Object.entries(patterns)
    .filter(([_, data]) => data.detected)
    .map(([name, data]) => ({
      name: name.replace(/_/g, " ").toUpperCase(),
      confidence: Math.round((data.confidence || 0) * 100),
    }));

  return (
    <div className="space-y-8">
      {/* IP Threats Analysis */}
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-semibold mb-4 text-blue-400">IP Threat Analysis</h3>
        <div className="grid grid-cols-2 gap-6">
          <div>
            <div className="text-4xl font-bold text-red-400 mb-2">
              {(threat_components.ip_threats.threat_score * 100).toFixed(1)}%
            </div>
            <p className="text-gray-400">Threat Score</p>
          </div>
          <div>
            <div className="text-4xl font-bold text-orange-400 mb-2">
              {threat_components.ip_threats.suspicious_ips}
            </div>
            <p className="text-gray-400">Suspicious IPs</p>
          </div>
        </div>

        {threat_components.ip_threats.threat_categories.length > 0 && (
          <div className="mt-6">
            <p className="text-gray-300 font-medium mb-3">Detected Threat Categories:</p>
            <div className="flex flex-wrap gap-2">
              {threat_components.ip_threats.threat_categories.map((category) => (
                <span
                  key={category}
                  className="bg-red-500 bg-opacity-20 text-red-300 px-3 py-1 rounded text-sm"
                >
                  {category.toUpperCase()}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Behavioral Analysis */}
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-semibold mb-4 text-yellow-400">Behavioral Analysis</h3>
        <div className="grid grid-cols-2 gap-6 mb-6">
          <div>
            <div className="text-4xl font-bold text-yellow-400 mb-2">
              {(threat_components.behavioral.behavioral_threat_score * 100).toFixed(1)}%
            </div>
            <p className="text-gray-400">Behavior Risk</p>
          </div>
          <div>
            <div className="text-4xl font-bold text-yellow-400 mb-2">
              {threat_components.behavioral.patterns_detected.length}
            </div>
            <p className="text-gray-400">Patterns Detected</p>
          </div>
        </div>

        {patternData.length > 0 && (
          <div className="mt-6">
            <p className="text-gray-300 font-medium mb-3">Detected Patterns:</p>
            <div className="space-y-3">
              {patternData.map((pattern) => (
                <div key={pattern.name} className="flex items-center gap-3">
                  <div className="text-sm font-medium text-gray-300 w-48">{pattern.name}</div>
                  <div className="flex-1 bg-gray-700 rounded-full h-2 overflow-hidden">
                    <div
                      className="h-full bg-yellow-500"
                      style={{ width: `${pattern.confidence}%` }}
                    ></div>
                  </div>
                  <div className="text-sm text-gray-400 w-12 text-right">{pattern.confidence}%</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Chat Intelligence */}
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-semibold mb-4 text-cyan-400">Chat Intelligence</h3>
        <div className="grid grid-cols-2 gap-6">
          <div>
            <div className="text-4xl font-bold text-cyan-400 mb-2">
              {(threat_components.chat.chat_threat_score * 100).toFixed(1)}%
            </div>
            <p className="text-gray-400">Chat Threat Score</p>
          </div>
          <div>
            <div className="text-4xl font-bold text-orange-400 mb-2">
              {threat_components.chat.spam_indicators}
            </div>
            <p className="text-gray-400">Spam Indicators</p>
          </div>
        </div>

        {threat_components.chat.coordinated_spam_detected && (
          <div className="mt-4 p-3 bg-orange-500 bg-opacity-10 border border-orange-500 border-opacity-30 rounded">
            <p className="text-orange-300 text-sm font-medium">
              ⚠️ Coordinated spam attack detected
            </p>
          </div>
        )}
      </div>

      {/* Threat Score Distribution */}
      {threatScoreData.some((d) => d.value > 0) && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-semibold mb-4">Threat Score Distribution</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={threatScoreData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, value }) => `${name}: ${value}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {COLORS.map((color, index) => (
                  <Cell key={`cell-${index}`} fill={color} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => `${value}%`} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Graph Correlation Analysis */}
      {threat_components.graph_correlation && threat_components.graph_correlation.detected_clusters > 0 && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-semibold mb-4 text-purple-400">Graph Correlation</h3>
          <div className="grid grid-cols-3 gap-6">
            <div>
              <div className="text-3xl font-bold text-purple-400 mb-2">
                {threat_components.graph_correlation.detected_clusters}
              </div>
              <p className="text-gray-400">Detected Clusters</p>
            </div>
            <div>
              <div className="text-3xl font-bold text-purple-400 mb-2">
                {(threat_components.graph_correlation.coordination_score * 100).toFixed(1)}%
              </div>
              <p className="text-gray-400">Coordination Score</p>
            </div>
          </div>
          <p className="text-sm text-gray-400 mt-4">
            Multiple coordinated clusters detected. This indicates organized attack activity.
          </p>
        </div>
      )}
    </div>
  );
}
