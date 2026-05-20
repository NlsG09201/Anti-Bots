import { cn } from "@/lib/utils";

const variants = {
  default: "bg-cyber-accent/15 text-cyber-accent border-cyber-accent/30",
  danger: "bg-cyber-danger/15 text-cyber-danger border-cyber-danger/30",
  warning: "bg-cyber-warning/15 text-cyber-warning border-cyber-warning/30",
  info: "bg-cyber-info/15 text-cyber-info border-cyber-info/30",
  muted: "bg-cyber-bg text-cyber-muted border-cyber-border",
};

export function Badge({
  className,
  variant = "default",
  children,
}: {
  className?: string;
  variant?: keyof typeof variants;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
        variants[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
