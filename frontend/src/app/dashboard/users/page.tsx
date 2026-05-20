"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Users, Shield, ShieldOff } from "lucide-react";
import clsx from "clsx";
import { api, TenantUser } from "@/lib/api";
import { useApiToken, useAuthStore } from "@/stores/authStore";

const ROLES = [
  { value: "viewer", label: "Viewer", color: "text-cyber-muted" },
  { value: "streamer", label: "Streamer", color: "text-blue-400" },
  { value: "analyst", label: "Analyst", color: "text-cyber-info" },
  { value: "admin", label: "Admin", color: "text-cyber-accent" },
  { value: "super_admin", label: "Super Admin", color: "text-yellow-400" },
];

export default function UsersPage() {
  const accessToken = useApiToken();
  const currentUser = useAuthStore((s) => s.user);
  const token = accessToken!;
  const queryClient = useQueryClient();

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["tenant-users"],
    queryFn: () => api.users.list(token),
    enabled: !!token,
  });

  const updateRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.users.updateRole(token, userId, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tenant-users"] }),
  });

  const updateStatus = useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      api.users.updateStatus(token, userId, isActive),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tenant-users"] }),
  });

  const roleLabel = (role: string) => ROLES.find((r) => r.value === role)?.label ?? role;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users className="text-cyber-accent" />
          Gestión de usuarios
        </h1>
        <p className="text-cyber-muted text-sm mt-1">
          RBAC — asigna roles sin tocar la base de datos
        </p>
      </div>

      <div className="cyber-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border">
              <th className="text-left py-3 px-2">Usuario</th>
              <th className="text-left py-3 px-2">Email</th>
              <th className="text-left py-3 px-2">Rol</th>
              <th className="text-center py-3 px-2">MFA</th>
              <th className="text-center py-3 px-2">Estado</th>
              <th className="text-right py-3 px-2">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr
                key={u.id}
                className={clsx(
                  "border-b border-cyber-border/50",
                  u.id === currentUser?.id && "bg-cyber-accent/5",
                )}
              >
                <td className="py-3 px-2 text-white font-medium">
                  {u.username}
                  {u.id === currentUser?.id && (
                    <span className="ml-2 text-xs text-cyber-accent">(tú)</span>
                  )}
                </td>
                <td className="py-3 px-2 text-cyber-muted">{u.email}</td>
                <td className="py-3 px-2">
                  {u.id === currentUser?.id ? (
                    <span className="text-cyber-accent capitalize">{roleLabel(u.role)}</span>
                  ) : (
                    <select
                      value={u.role}
                      onChange={(e) =>
                        updateRole.mutate({ userId: u.id, role: e.target.value })
                      }
                      disabled={updateRole.isPending}
                      className="bg-cyber-bg border border-cyber-border rounded px-2 py-1 text-white text-xs capitalize"
                    >
                      {ROLES.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  )}
                </td>
                <td className="py-3 px-2 text-center">
                  {u.mfa_enabled ? (
                    <Shield size={16} className="inline text-cyber-accent" />
                  ) : (
                    <ShieldOff size={16} className="inline text-cyber-muted" />
                  )}
                </td>
                <td className="py-3 px-2 text-center">
                  <span
                    className={clsx(
                      "text-xs px-2 py-0.5 rounded",
                      u.is_active
                        ? "bg-cyber-accent/10 text-cyber-accent"
                        : "bg-cyber-danger/10 text-cyber-danger",
                    )}
                  >
                    {u.is_active ? "Activo" : "Inactivo"}
                  </span>
                </td>
                <td className="py-3 px-2 text-right">
                  {u.id !== currentUser?.id && (
                    <button
                      onClick={() =>
                        updateStatus.mutate({ userId: u.id, isActive: !u.is_active })
                      }
                      disabled={updateStatus.isPending}
                      className={clsx(
                        "text-xs px-3 py-1 rounded border transition-colors",
                        u.is_active
                          ? "border-cyber-danger/30 text-cyber-danger hover:bg-cyber-danger/10"
                          : "border-cyber-accent/30 text-cyber-accent hover:bg-cyber-accent/10",
                      )}
                    >
                      {u.is_active ? "Desactivar" : "Activar"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && (
          <p className="text-center py-8 text-cyber-muted">Cargando usuarios...</p>
        )}
        {!isLoading && users.length === 0 && (
          <p className="text-center py-8 text-cyber-muted">No hay usuarios</p>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {ROLES.map((r) => (
          <div key={r.value} className="cyber-card p-3 text-center">
            <p className={clsx("text-xs font-semibold capitalize", r.color)}>{r.label}</p>
            <p className="text-lg font-bold text-white mt-1">
              {users.filter((u) => u.role === r.value).length}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
