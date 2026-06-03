/**
 * Threat Map Component - Geolocation visualization
 */

"use client";

import React, { useEffect, useState } from "react";

interface GeoLocation {
  country: string;
  country_code: string;
  city?: string;
  viewer_count: number;
  suspicious_count: number;
  avg_threat_score: number;
}

interface ThreatMapProps {
  streamId: string;
}

export default function ThreatMap({ streamId }: ThreatMapProps) {
  const [locations, setLocations] = useState<GeoLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [topCountries, setTopCountries] = useState<GeoLocation[]>([]);

  useEffect(() => {
    fetchLocations();
    const interval = setInterval(fetchLocations, 15000); // Refresh every 15 seconds
    return () => clearInterval(interval);
  }, [streamId]);

  const fetchLocations = async () => {
    try {
      const response = await fetch(
        `/api/v1/threat-intelligence/threat-analysis/${streamId}`
      );
      const data = await response.json();
      const geoData = data.analysis?.geolocation || [];
      setLocations(geoData);
      
      // Get top 10 countries
      const top = geoData
        .sort((a: GeoLocation, b: GeoLocation) => b.viewer_count - a.viewer_count)
        .slice(0, 10);
      setTopCountries(top);
    } catch (error) {
      console.error("Failed to fetch locations:", error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-gray-400">Loading geolocation data...</div>;
  }

  const totalViewers = locations.reduce((sum, loc) => sum + loc.viewer_count, 0);
  const totalSuspicious = locations.reduce((sum, loc) => sum + loc.suspicious_count, 0);

  return (
    <div className="space-y-6">
      {/* Global Statistics */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
          <div className="text-gray-400 text-sm mb-2">Total Locations</div>
          <div className="text-3xl font-bold text-white">{locations.length}</div>
          <div className="text-xs text-gray-500 mt-2">Countries</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
          <div className="text-gray-400 text-sm mb-2">Global Viewers</div>
          <div className="text-3xl font-bold text-white">{totalViewers}</div>
          <div className="text-xs text-gray-500 mt-2">Across all regions</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
          <div className="text-gray-400 text-sm mb-2">Suspicious Locations</div>
          <div className="text-3xl font-bold text-orange-400">{totalSuspicious}</div>
          <div className="text-xs text-gray-500 mt-2">Potential threats</div>
        </div>
      </div>

      {/* Top Countries */}
      <div>
        <h3 className="text-lg font-semibold mb-4">Top Countries by Viewers</h3>
        <div className="space-y-3">
          {topCountries.map((location) => {
            const suspiciousRatio = (location.suspicious_count / location.viewer_count) * 100;
            return (
              <div key={location.country_code} className="bg-gray-900 rounded-lg p-4 border border-gray-700">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <h4 className="font-semibold text-white text-lg">
                      {location.country} ({location.country_code.toUpperCase()})
                    </h4>
                    {location.city && (
                      <p className="text-sm text-gray-400">{location.city}</p>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-white">{location.viewer_count}</div>
                    <div className="text-xs text-gray-400">viewers</div>
                  </div>
                </div>

                {/* Progress bars */}
                <div className="space-y-2">
                  <div>
                    <div className="flex justify-between mb-1">
                      <span className="text-xs text-gray-400">Suspicious Ratio</span>
                      <span className="text-xs text-gray-400 font-mono">{suspiciousRatio.toFixed(1)}%</span>
                    </div>
                    <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
                      <div
                        className={`h-full transition-all ${
                          suspiciousRatio > 50
                            ? "bg-red-500"
                            : suspiciousRatio > 25
                            ? "bg-orange-500"
                            : "bg-yellow-500"
                        }`}
                        style={{ width: `${suspiciousRatio}%` }}
                      ></div>
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between mb-1">
                      <span className="text-xs text-gray-400">Avg Threat Score</span>
                      <span className={`text-xs font-mono font-semibold ${
                        location.avg_threat_score >= 0.6
                          ? "text-orange-400"
                          : location.avg_threat_score >= 0.4
                          ? "text-yellow-400"
                          : "text-green-400"
                      }`}>
                        {(location.avg_threat_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
                      <div
                        className={`h-full ${
                          location.avg_threat_score >= 0.6
                            ? "bg-orange-500"
                            : location.avg_threat_score >= 0.4
                            ? "bg-yellow-500"
                            : "bg-green-500"
                        }`}
                        style={{ width: `${location.avg_threat_score * 100}%` }}
                      ></div>
                    </div>
                  </div>
                </div>

                {/* Stats */}
                <div className="mt-3 pt-3 border-t border-gray-700 grid grid-cols-2 gap-2 text-xs">
                  <div className="text-gray-400">
                    <span className="font-semibold text-white">{location.suspicious_count}</span> suspicious
                  </div>
                  <div className="text-gray-400 text-right">
                    <span className="font-semibold text-white">{location.viewer_count - location.suspicious_count}</span> legitimate
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Risk by Region */}
      {locations.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-4">High-Risk Regions</h3>
          <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
            {locations
              .filter((loc) => (loc.suspicious_count / loc.viewer_count) * 100 > 30)
              .sort((a, b) => (b.suspicious_count / b.viewer_count) - (a.suspicious_count / a.viewer_count))
              .slice(0, 5)
              .map((location) => (
                <div key={location.country_code} className="flex justify-between items-center py-2 border-b border-gray-700 last:border-0">
                  <span className="font-medium">{location.country}</span>
                  <span className="text-orange-400 font-semibold">
                    {location.suspicious_count} / {location.viewer_count} at risk
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
