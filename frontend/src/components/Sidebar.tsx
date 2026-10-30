"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, AlertTriangle, Ban, Binary, Bot, Brain, ChevronDown, Code, DatabaseZap,
  Fingerprint, Globe, LayoutDashboard, LogOut, MessageSquare, Radio, Radar, Rocket,
  Settings, Shield, ShieldAlert, Users, X,
} from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import clsx from "clsx";

const navGroups = [
  {
    label: "Workspace",
    items: [
      { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
      { href: "/dashboard/channels", label: "Channels", icon: Radio },
      { href: "/dashboard/alerts", label: "Alerts", icon: Shield },
    ],
  },
  {
    label: "Protection",
    items: [
      { href: "/dashboard/attacks", label: "Attacks", icon: AlertTriangle },
      { href: "/dashboard/bans", label: "Bans", icon: Ban },
      { href: "/dashboard/viewers", label: "Viewers", icon: Users },
      { href: "/dashboard/viewer-flow", label: "Viewer flow", icon: Activity },
      { href: "/dashboard/bot", label: "Kick bot", icon: Bot },
      { href: "/dashboard/twitch-moderator", label: "Twitch moderator", icon: ShieldAlert },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/dashboard/security", label: "Security center", icon: ShieldAlert },
      { href: "/dashboard/threat-intelligence", label: "Threat intelligence", icon: Radar },
      { href: "/dashboard/live-intelligence", label: "Live intelligence", icon: Radio },
      { href: "/dashboard/ai", label: "AI predictions", icon: Brain },
      { href: "/dashboard/assistant", label: "SOC assistant", icon: MessageSquare },
      { href: "/dashboard/power-bi", label: "Power BI", icon: DatabaseZap },
      { href: "/dashboard/weka", label: "Weka J48", icon: Binary },
      { href: "/dashboard/ips", label: "Suspicious IPs", icon: Globe },
      { href: "/dashboard/fingerprints", label: "Fingerprints", icon: Fingerprint },
    ],
  },
  {
    label: "Administration",
    items: [
      { href: "/dashboard/widget", label: "Widget", icon: Code },
      { href: "/dashboard/users", label: "Users", icon: Users },
      { href: "/dashboard/settings", label: "Settings", icon: Settings },
      { href: "/dashboard/deploy", label: "Deployment", icon: Rocket },
    ],
  },
];

export function getDashboardPageTitle(pathname: string) {
  return navGroups.flatMap((group) => group.items).find((item) => item.href === pathname)?.label
    ?? "Security workspace";
}

export function Sidebar({
  mobileOpen = false,
  onClose,
}: {
  mobileOpen?: boolean;
  onClose?: () => void;
}) {
  const pathname = usePathname();
  const { logout, user } = useAuthStore();

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={onClose}
          className="fixed inset-0 z-40 bg-slate-950/55 backdrop-blur-sm md:hidden"
        />
      )}
      <aside
        id="primary-navigation"
        className={clsx(
          "fixed inset-y-0 left-0 z-50 flex h-dvh w-[min(19rem,88vw)] -translate-x-full flex-col border-r border-cyber-border bg-cyber-surface shadow-2xl transition-transform duration-200 md:sticky md:top-0 md:z-20 md:h-screen md:w-64 md:translate-x-0 md:shadow-none",
          mobileOpen && "translate-x-0",
        )}
      >
        <div className="flex h-[4.5rem] shrink-0 items-center justify-between border-b border-cyber-border px-5">
          <Link href="/dashboard" prefetch={false} onClick={onClose} className="flex items-center gap-3 rounded-md focus-visible:outline-none">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-cyber-accent/10 text-cyber-accent ring-1 ring-cyber-accent/20">
              <Shield size={19} strokeWidth={2.2} />
            </span>
            <span>
              <span className="block text-sm font-semibold tracking-tight text-cyber-text">StreamShield</span>
              <span className="block text-[10px] font-medium uppercase tracking-[0.16em] text-cyber-muted">Live protection</span>
            </span>
          </Link>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="rounded-lg p-2 text-cyber-muted hover:bg-cyber-surface-elevated hover:text-cyber-text md:hidden"
          >
            <X size={18} />
          </button>
        </div>

        <nav aria-label="Main navigation" className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-4">
          {navGroups.map((group) => {
            const activeGroup = group.items.some((item) => item.href === pathname);
            return (
              <details key={group.label} open={activeGroup || group.label === "Workspace"} className="group">
                <summary className="flex cursor-pointer list-none items-center justify-between rounded-md px-2 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-cyber-muted hover:text-cyber-text [&::-webkit-details-marker]:hidden">
                  {group.label}
                  <ChevronDown size={13} className="transition-transform group-open:rotate-180" />
                </summary>
                <div className="mt-1 space-y-0.5">
                  {group.items.map(({ href, label, icon: Icon }) => {
                    const active = pathname === href;
                    return (
                      <Link
                        key={href}
                        href={href}
                        prefetch={false}
                        onClick={onClose}
                        aria-current={active ? "page" : undefined}
                        className={clsx(
                          "flex min-h-10 items-center gap-3 rounded-lg px-3 text-[13px] font-medium transition-colors",
                          active
                            ? "bg-cyber-accent/10 text-cyber-accent ring-1 ring-inset ring-cyber-accent/20"
                            : "text-cyber-muted hover:bg-cyber-surface-elevated hover:text-cyber-text",
                        )}
                      >
                        <Icon size={16} strokeWidth={1.8} />
                        <span>{label}</span>
                      </Link>
                    );
                  })}
                </div>
              </details>
            );
          })}
        </nav>

        <div className="shrink-0 border-t border-cyber-border p-4">
          <p className="mb-3 truncate text-xs text-cyber-muted" title={user?.email ?? undefined}>
            {user?.email || "Signed in"}
          </p>
          <button
            type="button"
            onClick={logout}
            className="flex min-h-10 w-full items-center gap-2 rounded-lg px-3 text-sm font-medium text-cyber-muted transition-colors hover:bg-cyber-danger/10 hover:text-cyber-danger"
          >
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      </aside>
    </>
  );
}
