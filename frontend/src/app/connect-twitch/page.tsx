"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { resolveApiBaseUrl } from "@/lib/runtime-urls";

function ConnectContent() {
  const searchParams = useSearchParams();
  const invite = searchParams.get("invite");
  const error = invite ? "" : "Falta el token de invitacion.";

  useEffect(() => {
    if (!invite) return;
    const api = resolveApiBaseUrl();
    // This API endpoint starts OAuth and redirects to Twitch; a full navigation is required.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `${api}/api/v1/integrations/twitch/invite/${encodeURIComponent(invite)}/start`;
  }, [invite]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-cyber-bg p-6">
      <div className="cyber-card max-w-md w-full p-8 text-center">
        <h1 className="text-xl font-bold text-white mb-2">Conectar Twitch</h1>
        {error ? (
          <p className="text-cyber-danger text-sm">{error}</p>
        ) : (
          <p className="text-cyber-muted text-sm">
            Redirigiendo a Twitch para autorizar StreamShield en este canal...
          </p>
        )}
      </div>
    </div>
  );
}

export default function ConnectTwitchPage() {
  return (
    <Suspense fallback={<p className="text-cyber-muted p-8 text-center">Cargando...</p>}>
      <ConnectContent />
    </Suspense>
  );
}
