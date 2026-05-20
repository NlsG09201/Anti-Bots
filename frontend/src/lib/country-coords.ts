/** Centroides aproximados para el mapa de amenazas (ISO 3166-1 alpha-2). */
export const COUNTRY_COORDS: Record<string, { lat: number; lng: number; label: string }> = {
  US: { lat: 39.8, lng: -98.5, label: "United States" },
  CA: { lat: 56.1, lng: -106.3, label: "Canada" },
  MX: { lat: 23.6, lng: -102.5, label: "Mexico" },
  BR: { lat: -14.2, lng: -51.9, label: "Brazil" },
  AR: { lat: -38.4, lng: -63.6, label: "Argentina" },
  GB: { lat: 55.4, lng: -3.4, label: "United Kingdom" },
  DE: { lat: 51.2, lng: 10.5, label: "Germany" },
  FR: { lat: 46.2, lng: 2.2, label: "France" },
  ES: { lat: 40.5, lng: -3.7, label: "Spain" },
  IT: { lat: 41.9, lng: 12.6, label: "Italy" },
  NL: { lat: 52.1, lng: 5.3, label: "Netherlands" },
  PL: { lat: 51.9, lng: 19.1, label: "Poland" },
  RU: { lat: 61.5, lng: 105.3, label: "Russia" },
  UA: { lat: 48.4, lng: 31.2, label: "Ukraine" },
  TR: { lat: 38.9, lng: 35.2, label: "Turkey" },
  IN: { lat: 20.6, lng: 78.9, label: "India" },
  CN: { lat: 35.9, lng: 104.2, label: "China" },
  JP: { lat: 36.2, lng: 138.3, label: "Japan" },
  KR: { lat: 35.9, lng: 127.8, label: "South Korea" },
  AU: { lat: -25.3, lng: 133.8, label: "Australia" },
  ID: { lat: -0.8, lng: 113.9, label: "Indonesia" },
  SG: { lat: 1.35, lng: 103.8, label: "Singapore" },
  AE: { lat: 23.4, lng: 53.8, label: "UAE" },
  SA: { lat: 23.9, lng: 45.1, label: "Saudi Arabia" },
  ZA: { lat: -30.6, lng: 22.9, label: "South Africa" },
  NG: { lat: 9.1, lng: 8.7, label: "Nigeria" },
  EG: { lat: 26.8, lng: 30.8, label: "Egypt" },
  CL: { lat: -35.7, lng: -71.5, label: "Chile" },
  CO: { lat: 4.6, lng: -74.3, label: "Colombia" },
  SE: { lat: 60.1, lng: 18.6, label: "Sweden" },
  NO: { lat: 60.5, lng: 8.5, label: "Norway" },
  FI: { lat: 61.9, lng: 25.7, label: "Finland" },
  RO: { lat: 45.9, lng: 24.9, label: "Romania" },
  PT: { lat: 39.4, lng: -8.2, label: "Portugal" },
  IE: { lat: 53.4, lng: -8.2, label: "Ireland" },
  VN: { lat: 14.1, lng: 108.3, label: "Vietnam" },
  TH: { lat: 15.9, lng: 100.9, label: "Thailand" },
  PH: { lat: 12.9, lng: 121.8, label: "Philippines" },
};

export function projectLatLng(
  lat: number,
  lng: number,
  width: number,
  height: number,
): { x: number; y: number } {
  const x = ((lng + 180) / 360) * width;
  const y = ((90 - lat) / 180) * height;
  return { x, y };
}
