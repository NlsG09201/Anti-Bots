"use client";

import Link from "next/link";
import {
  Globe,
  Radio,
  Settings,
  Shield,
  Users,
  Workflow,
} from "lucide-react";
import type { SecurityDashboard } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/authStore";

const adminLinks = [
  { href: "/dashboard/users", label: "Usuarios", icon: Users },
  { href: "/dashboard/channels", label: "Canales", icon: Radio },
  { href: "/dashboard/ips", label: "Threat intel IPs", icon: Globe },
  { href: "/dashboard/security", label: "Security SOC", icon: Shield },
  { href: "/dashboard/settings", label: "Configuración", icon: Settings },
];

interface AdminPanelProps {
  security?: SecurityDashboard;
}

export function AdminPanel({ security }: AdminPanelProps) {
  const { user } = useAuthStore();
  const isAdmin = user?.role === "admin" || user?.role === "super_admin";

  return (
    <div className="rounded-xl border border-cyber-border/80 bg-gradient-to-br from-cyber-surface/90 to-cyber-bg/50 p-5">
      <div className="flex items-center gap-2 mb-4">
        <Workflow size={18} className="text-cyber-accent" />
        <p className="text-xs uppercase tracking-widest text-cyber-muted">Panel administrativo</p>
      </div>
      <p className="text-sm text-white font-medium">{user?.email}</p>
      <p className="text-xs text-cyber-muted mt-1 capitalize">Rol: {user?.role ?? "—"}</p>

      {security && (
        <div className="mt-4 grid grid-cols-2 gap-2 text-center">
          <div className="rounded-lg border border-cyber-border/50 py-2 px-2">
            <p className="text-lg font-mono font-bold text-cyber-danger">
              {security.summary.proxy_detections}
            </p>
            <p className="text-[10px] text-cyber-muted">Proxy</p>
          </div>
          <div className="rounded-lg border border-cyber-border/50 py-2 px-2">
            <p className="text-lg font-mono font-bold text-cyber-warning">
              {security.summary.vpn_detections}
            </p>
            <p className="text-[10px] text-cyber-muted">VPN</p>
          </div>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 gap-2">
        {adminLinks.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href}>
            <Button variant="outline" size="sm" className="w-full justify-start">
              <Icon size={16} />
              {label}
            </Button>
          </Link>
        ))}
      </div>

      {!isAdmin && (
        <p className="text-[10px] text-cyber-muted mt-3">
          Algunas acciones requieren rol analyst/admin.
        </p>
      )}
    </div>
  );
}
