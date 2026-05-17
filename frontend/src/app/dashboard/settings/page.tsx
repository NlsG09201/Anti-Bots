"use client";

import { Suspense, useEffect, useState } from "react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shield, Tv, CheckCircle, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

function SettingsContent() {
  const searchParams = useSearchParams();
  const { accessToken, user } = useAuthStore();
  const token = accessToken!;
  const queryClient = useQueryClient();

  const [mfaCode, setMfaCode] = useState("");
  const [setupData, setSetupData] = useState<{
    qr_code_base64: string;
    provisioning_uri: string;
  } | null>(null);
  const [message, setMessage] = useState("");

  const isAdmin =
    user?.role === "admin" || user?.role === "super_admin" || user?.role === "analyst";

  useEffect(() => {
    if (searchParams.get("twitch") === "connected") {
      setMessage("Twitch conectado correctamente. EventSub suscripciones activadas.");
      queryClient.invalidateQueries({ queryKey: ["twitch-status"] });
    }
    const twitchError = searchParams.get("twitch_error");
    if (twitchError) {
      const detail = searchParams.get("twitch_msg") || twitchError;
      setMessage(
        twitchError === "redirect_mismatch"
          ? `Twitch: la Redirect URI no coincide. En dev.twitch.tv añade exactamente: https://anti-bots.onrender.com/api/v1/integrations/twitch/callback (${detail})`
          : `Error Twitch (${twitchError}): ${detail}`,
      );
    }
  }, [searchParams, queryClient]);

  const { data: mfaStatus } = useQuery({
    queryKey: ["mfa-status"],
    queryFn: () => api.mfa.status(token),
    enabled: !!token && isAdmin,
  });

  const { data: twitchStatus } = useQuery({
    queryKey: ["twitch-status"],
    queryFn: () => api.twitch.status(token),
    enabled: !!token,
  });

  const { data: twitchSetup } = useQuery({
    queryKey: ["twitch-setup"],
    queryFn: () => api.twitch.setup(token),
    enabled: !!token,
  });

  const setupMfa = useMutation({
    mutationFn: () => api.mfa.setup(token),
    onSuccess: (data) => setSetupData(data),
  });

  const enableMfa = useMutation({
    mutationFn: () => api.mfa.enable(token, mfaCode),
    onSuccess: () => {
      setMessage("MFA activado correctamente");
      setSetupData(null);
      setMfaCode("");
      queryClient.invalidateQueries({ queryKey: ["mfa-status"] });
    },
  });

  const disableMfa = useMutation({
    mutationFn: () => api.mfa.disable(token, mfaCode),
    onSuccess: () => {
      setMessage("MFA desactivado");
      setMfaCode("");
      queryClient.invalidateQueries({ queryKey: ["mfa-status"] });
    },
  });

  const connectTwitch = useMutation({
    mutationFn: () => api.twitch.authorize(token),
    onSuccess: (data) => {
      if (!data.authorization_url) {
        setMessage("No se recibió URL de autorización de Twitch.");
        return;
      }
      window.location.href = data.authorization_url;
    },
    onError: (err: unknown) => {
      setMessage(err instanceof Error ? err.message : "Error al conectar con Twitch");
    },
  });

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Configuración</h1>
        <p className="text-cyber-muted text-sm mt-1">Integraciones y seguridad de cuenta</p>
      </div>

      {message && (
        <div className="cyber-card flex items-center gap-3 text-cyber-accent border-cyber-accent/30">
          <CheckCircle size={20} />
          <p className="text-sm">{message}</p>
        </div>
      )}

      <section className="cyber-card space-y-4">
        <div className="flex items-center gap-3">
          <Tv className="text-purple-400" size={24} />
          <div>
            <h2 className="font-semibold text-white">Twitch</h2>
            <p className="text-xs text-cyber-muted">
              Conecta tu canal para EventSub y detección en vivo
            </p>
          </div>
        </div>

        {twitchSetup && !twitchSetup.credentials_ok && (
          <div className="p-4 rounded-lg bg-cyber-danger/10 border border-cyber-danger/40 space-y-3 text-sm text-red-300">
            <p className="font-semibold text-red-400 flex items-center gap-2">
              <AlertCircle size={16} />
              Credenciales Twitch inválidas en Render
            </p>
            {twitchSetup.client_id_equals_secret && (
              <p>
                El Client ID y el Client Secret son <strong>iguales</strong> (valores de plantilla).
                Twitch rechaza la conexión con <code>redirect_mismatch</code>.
              </p>
            )}
            <ol className="list-decimal list-inside space-y-1 text-cyber-muted">
              <li>
                Crea una app en{" "}
                <a href="https://dev.twitch.tv/console/apps" target="_blank" rel="noreferrer" className="text-cyber-info underline">
                  dev.twitch.tv
                </a>
              </li>
              <li>
                OAuth Redirect URL (copiar tal cual):<br />
                <code className="text-cyber-accent break-all">{twitchSetup.redirect_uri}</code>
              </li>
              <li>
                En Render → Environment: <code>TWITCH_CLIENT_ID</code> y <code>TWITCH_CLIENT_SECRET</code>{" "}
                (deben ser <strong>diferentes</strong>)
              </li>
              <li>Manual Deploy en Render y vuelve a conectar</li>
            </ol>
          </div>
        )}

        {twitchStatus?.connected ? (
          <div className="space-y-2">
            {twitchStatus.channels.map((ch) => (
              <div
                key={ch.id}
                className="flex items-center justify-between p-3 bg-cyber-bg rounded border border-cyber-border"
              >
                <span className="text-white font-medium">{ch.channel_name}</span>
                <span
                  className={
                    ch.is_live ? "text-cyber-accent text-xs" : "text-cyber-muted text-xs"
                  }
                >
                  {ch.is_live ? "EN VIVO" : "Offline"}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <button
            onClick={() => connectTwitch.mutate()}
            disabled={!twitchStatus?.configured || connectTwitch.isPending}
            className="cyber-btn-primary"
          >
            {connectTwitch.isPending ? "Redirigiendo..." : "Conectar con Twitch"}
          </button>
        )}

        <p className="text-xs text-cyber-muted">
          Redirect URI en{" "}
          <a
            href="https://dev.twitch.tv/console/apps"
            target="_blank"
            rel="noopener noreferrer"
            className="text-cyber-info hover:underline"
          >
            Twitch Developer Console
          </a>
          :{" "}
          <code className="text-cyber-info break-all">
            https://anti-bots.onrender.com/api/v1/integrations/twitch/callback
          </code>
        </p>
      </section>

      {isAdmin && (
        <section className="cyber-card space-y-4">
          <div className="flex items-center gap-3">
            <Shield className="text-cyber-accent" size={24} />
            <div>
              <h2 className="font-semibold text-white">Autenticación MFA</h2>
              <p className="text-xs text-cyber-muted">
                Recomendado para admin/analyst — Google Authenticator, Authy
              </p>
            </div>
          </div>

          <p className="text-sm text-cyber-muted">
            Estado:{" "}
            <span className={mfaStatus?.enabled ? "text-cyber-accent" : "text-cyber-warning"}>
              {mfaStatus?.enabled ? "Activado" : "Desactivado"}
            </span>
          </p>

          {!mfaStatus?.enabled && !setupData && (
            <button
              onClick={() => setupMfa.mutate()}
              className="cyber-btn-primary"
              disabled={setupMfa.isPending}
            >
              Configurar MFA
            </button>
          )}

          {setupData && (
            <div className="space-y-4">
              <Image
                src={`data:image/png;base64,${setupData.qr_code_base64}`}
                alt="MFA QR"
                width={192}
                height={192}
                unoptimized
                className="mx-auto w-48 h-48 rounded border border-cyber-border"
              />
              <input
                type="text"
                placeholder="Código de 6 dígitos"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                className="w-full px-4 py-3 bg-cyber-bg border border-cyber-border rounded-md text-white text-center font-mono text-xl tracking-widest"
              />
              <button
                onClick={() => enableMfa.mutate()}
                disabled={mfaCode.length !== 6 || enableMfa.isPending}
                className="w-full cyber-btn-primary"
              >
                Activar MFA
              </button>
            </div>
          )}

          {mfaStatus?.enabled && (
            <div className="space-y-3">
              <input
                type="text"
                placeholder="Código para desactivar"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                className="w-full px-4 py-3 bg-cyber-bg border border-cyber-border rounded-md text-white text-center font-mono"
              />
              <button
                onClick={() => disableMfa.mutate()}
                disabled={mfaCode.length !== 6}
                className="cyber-btn-danger w-full"
              >
                Desactivar MFA
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<p className="text-cyber-muted">Cargando...</p>}>
      <SettingsContent />
    </Suspense>
  );
}
