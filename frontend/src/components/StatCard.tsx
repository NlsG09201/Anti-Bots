import { LucideIcon } from "lucide-react";
import clsx from "clsx";

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  trend?: string;
  variant?: "default" | "danger" | "warning" | "success";
}

export function StatCard({ title, value, icon: Icon, trend, variant = "default" }: StatCardProps) {
  const variants = {
    default: "border-cyber-border",
    danger: "border-cyber-danger/30 bg-cyber-danger/5",
    warning: "border-cyber-warning/30 bg-cyber-warning/5",
    success: "border-cyber-accent/30 bg-cyber-accent/5",
  };

  const iconColors = {
    default: "text-cyber-info",
    danger: "text-cyber-danger",
    warning: "text-cyber-warning",
    success: "text-cyber-accent",
  };

  return (
    <div className={clsx("cyber-card", variants[variant])}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-cyber-muted">{title}</p>
          <p className="text-3xl font-bold text-white mt-1 font-mono">{value}</p>
          {trend && <p className="text-xs text-cyber-muted mt-1">{trend}</p>}
        </div>
        <div className={clsx("p-2 rounded-lg bg-cyber-bg", iconColors[variant])}>
          <Icon size={24} />
        </div>
      </div>
    </div>
  );
}
