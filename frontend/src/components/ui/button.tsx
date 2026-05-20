import { cn } from "@/lib/utils";

const variants = {
  default:
    "bg-cyber-accent text-cyber-bg hover:bg-green-400 shadow-[0_0_20px_rgba(0,255,136,0.2)]",
  outline:
    "border border-cyber-border bg-transparent text-white hover:bg-cyber-bg/80",
  ghost: "text-cyber-muted hover:text-white hover:bg-cyber-bg/60",
  danger: "bg-cyber-danger/90 text-white hover:bg-red-500",
};

export function Button({
  className,
  variant = "default",
  size = "default",
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof variants;
  size?: "default" | "sm" | "icon";
}) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all cursor-pointer",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-accent/50",
        "disabled:opacity-50 disabled:pointer-events-none",
        variants[variant],
        size === "sm" && "px-3 py-1.5 text-xs",
        size === "default" && "px-4 py-2 text-sm",
        size === "icon" && "h-9 w-9 p-0",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
