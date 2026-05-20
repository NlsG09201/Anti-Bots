"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Shield, LayoutDashboard, AlertTriangle, Ban,
  Fingerprint, Globe, Users, Settings, LogOut, Rocket, Radio, Code, ShieldAlert,
} from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import clsx from "clsx";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/channels", label: "Channels", icon: Radio },
  { href: "/dashboard/attacks", label: "Attacks", icon: AlertTriangle },
  { href: "/dashboard/alerts", label: "Alerts", icon: Shield },
  { href: "/dashboard/security", label: "Security SOC", icon: ShieldAlert },
  { href: "/dashboard/viewers", label: "Viewers", icon: Users },
  { href: "/dashboard/widget", label: "Widget IP", icon: Code },
  { href: "/dashboard/ips", label: "Suspicious IPs", icon: Globe },
  { href: "/dashboard/fingerprints", label: "Fingerprints", icon: Fingerprint },
  { href: "/dashboard/bans", label: "Bans", icon: Ban },
  { href: "/dashboard/users", label: "Users", icon: Users },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
  { href: "/dashboard/deploy", label: "Deploy", icon: Rocket },
];

export function Sidebar() {
  const pathname = usePathname();
  const { logout, user } = useAuthStore();

  return (
    <aside className="w-64 min-h-screen bg-cyber-surface/95 backdrop-blur-md border-r border-cyber-border flex flex-col">
      <div className="p-6 border-b border-cyber-border bg-gradient-to-r from-cyber-accent/5 to-transparent">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyber-accent/10 border border-cyber-accent/20">
            <Shield className="w-7 h-7 text-cyber-accent" />
          </div>
          <div>
            <h1 className="font-bold text-white tracking-tight">
              Stream<span className="text-cyber-accent">Shield</span>
            </h1>
            <p className="text-[10px] uppercase tracking-widest text-cyber-muted">SOC · Live</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-200",
              pathname === href
                ? "bg-cyber-accent/10 text-cyber-accent border border-cyber-accent/25 shadow-[0_0_15px_rgba(0,255,136,0.08)]"
                : "text-cyber-muted hover:text-white hover:bg-cyber-bg/80",
            )}
          >
            <Icon size={18} />
            {label}
          </Link>
        ))}
      </nav>

      <div className="p-4 border-t border-cyber-border">
        <p className="text-xs text-cyber-muted mb-2 truncate">{user?.email}</p>
        <button
          onClick={logout}
          className="flex items-center gap-2 text-sm text-cyber-danger hover:text-red-400 transition-colors"
        >
          <LogOut size={16} />
          Cerrar sesión
        </button>
      </div>
    </aside>
  );
}
