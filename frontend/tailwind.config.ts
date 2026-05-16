import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: "#060a12",
          surface: "#0f1419",
          "surface-elevated": "#151b24",
          border: "#1e293b",
          accent: "#00ff88",
          danger: "#ff3366",
          warning: "#ffaa00",
          info: "#00aaff",
          muted: "#64748b",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      animation: {
        pulse_slow: "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        glow: "glow 2s ease-in-out infinite alternate",
      },
      keyframes: {
        glow: {
          "0%": { boxShadow: "0 0 5px #00ff88, 0 0 10px #00ff8844" },
          "100%": { boxShadow: "0 0 20px #00ff88, 0 0 30px #00ff8866" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
