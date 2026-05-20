"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/lib/utils";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={cn(
        "inline-flex items-center justify-center rounded-lg border border-cyber-border bg-cyber-surface/80 p-2 text-cyber-muted transition-colors hover:text-cyber-accent hover:border-cyber-accent/40 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-accent/50",
        className,
      )}
      aria-label={theme === "dark" ? "Activar modo claro" : "Activar modo oscuro"}
    >
      {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
