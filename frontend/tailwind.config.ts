import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: "rgb(var(--cyber-bg-rgb) / <alpha-value>)",
          surface: "rgb(var(--cyber-surface-rgb) / <alpha-value>)",
          "surface-elevated": "rgb(var(--cyber-surface-elevated-rgb) / <alpha-value>)",
          border: "rgb(var(--cyber-border-rgb) / <alpha-value>)",
          accent: "rgb(var(--cyber-accent-rgb) / <alpha-value>)",
          danger: "rgb(var(--cyber-danger-rgb) / <alpha-value>)",
          warning: "rgb(var(--cyber-warning-rgb) / <alpha-value>)",
          info: "rgb(var(--cyber-info-rgb) / <alpha-value>)",
          muted: "rgb(var(--cyber-muted-rgb) / <alpha-value>)",
          text: "rgb(var(--cyber-text-rgb) / <alpha-value>)",
          "on-accent": "rgb(var(--cyber-on-accent-rgb) / <alpha-value>)",
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
