"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Shield, Eye, EyeOff, Zap } from "lucide-react";
import { api, resetAuthSessionState } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

const TWITCH_CALLBACK =
  "https://anti-bots.onrender.com/api/v1/integrations/twitch/callback";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setTokens, setUser } = useAuthStore();
  const [isRegister, setIsRegister] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mfaStep, setMfaStep] = useState(false);
  const [mfaToken, setMfaToken] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [form, setForm] = useState({
    email: "",
    password: "",
    username: "",
    tenant_name: "",
  });

  useEffect(() => {
    if (searchParams.get("session") === "expired") {
      setError("Tu sesión expiró. Vuelve a iniciar sesión.");
    } else if (searchParams.get("error") === "redirect_mismatch") {
      setError(
        `Twitch: añade esta Redirect URI en dev.twitch.tv → OAuth Redirect URLs: ${TWITCH_CALLBACK}`,
      );
    } else if (searchParams.get("error")) {
      setError(
        searchParams.get("error_description") ||
          `OAuth: ${searchParams.get("error")}`,
      );
    }
  }, [searchParams]);

  const finishLogin = async (accessToken: string) => {
    resetAuthSessionState();
    setTokens(accessToken);
    const user = await api.auth.me(accessToken);
    setUser(user);
    router.push("/dashboard");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      if (mfaStep) {
        const data = await api.auth.verifyMfa(mfaToken, mfaCode);
        await finishLogin(data.access_token);
        return;
      }

      if (isRegister) {
        const tokens = await api.auth.register({
          email: form.email,
          password: form.password,
          username: form.username,
          tenant_name: form.tenant_name,
        });
        await finishLogin(tokens.access_token);
      } else {
        const tokens = await api.auth.login(form.email, form.password);
        if (tokens.mfa_required && tokens.mfa_token) {
          setMfaToken(tokens.mfa_token);
          setMfaStep(true);
          setLoading(false);
          return;
        }
        await finishLogin(tokens.access_token);
      }
    } catch (err: unknown) {
      if (err instanceof TypeError) {
        setError(
          "No se puede conectar con la API. Comprueba que Render esté Live, Upstash configurado y redeploy en Vercel.",
        );
      } else {
        setError(err instanceof Error ? err.message : "Error de autenticación");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center grid-pattern relative overflow-hidden">
      <div className="scan-line absolute inset-0 pointer-events-none opacity-50" />

      <div className="w-full max-w-md px-4 relative z-10">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-cyber-accent/20 to-cyber-info/10 border border-cyber-accent/30 mb-5 logo-pulse">
            <Shield className="w-10 h-10 text-cyber-accent" strokeWidth={1.5} />
          </div>
          <h1 className="text-4xl font-bold text-white tracking-tight">
            Stream<span className="text-cyber-accent">Shield</span>
          </h1>
          <p className="text-cyber-muted mt-2 flex items-center justify-center gap-2 text-sm">
            <Zap size={14} className="text-cyber-accent" />
            {mfaStep ? "Verificación en dos pasos" : "Protección anti-bot para streamers"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="cyber-card-glow space-y-4 border-cyber-accent/10">
          {error && (
            <div className="p-3 rounded-lg bg-cyber-danger/10 border border-cyber-danger/40 text-red-400 text-sm">
              {error}
            </div>
          )}

          {mfaStep ? (
            <>
              <p className="text-sm text-cyber-muted text-center">
                Código de tu app de autenticación
              </p>
              <input
                type="text"
                placeholder="000000"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                className="cyber-input text-center font-mono text-2xl tracking-[0.5em]"
                autoFocus
                required
              />
              <button
                type="button"
                onClick={() => { setMfaStep(false); setMfaCode(""); setMfaToken(""); }}
                className="w-full text-sm text-cyber-muted hover:text-cyber-accent"
              >
                ← Volver al login
              </button>
            </>
          ) : (
            <>
              {isRegister && (
                <>
                  <input
                    type="text"
                    placeholder="Nombre de usuario"
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    className="cyber-input"
                    required
                  />
                  <input
                    type="text"
                    placeholder="Nombre del canal / organización"
                    value={form.tenant_name}
                    onChange={(e) => setForm({ ...form, tenant_name: e.target.value })}
                    className="cyber-input"
                    required
                  />
                </>
              )}

              <input
                type="email"
                placeholder="correo@ejemplo.com"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="cyber-input"
                required
              />

              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder={isRegister ? "Contraseña (mín. 12 caracteres)" : "Contraseña"}
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="cyber-input pr-12"
                  required
                  minLength={isRegister ? 12 : 8}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>

              <button
                type="button"
                onClick={() => setIsRegister(!isRegister)}
                className="w-full text-sm text-cyber-muted hover:text-cyber-accent transition-colors"
              >
                {isRegister ? "¿Ya tienes cuenta? Iniciar sesión" : "¿Nuevo streamer? Crear cuenta gratis"}
              </button>
            </>
          )}

          <button
            type="submit"
            disabled={loading || (mfaStep && mfaCode.length !== 6)}
            className="w-full cyber-btn-primary py-3.5 text-base disabled:opacity-50 disabled:shadow-none"
          >
            {loading ? "Procesando..." : mfaStep ? "Verificar" : isRegister ? "Crear cuenta" : "Entrar al panel"}
          </button>
        </form>

        <p className="text-center text-xs text-slate-600 mt-6">
          Twitch · Kick · YouTube Live
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<p className="text-cyber-muted p-8">Cargando...</p>}>
      <LoginForm />
    </Suspense>
  );
}
