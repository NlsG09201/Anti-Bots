"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { useAuthStore } from "@/stores/authStore";
import { useWebSocketContext } from "@/contexts/WebSocketContext";
import { bootstrapAuthSession, getAccessToken } from "@/lib/api";
import { Wifi, WifiOff } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { setTokens, logout, isAuthenticated } = useAuthStore();
  const { connected } = useWebSocketContext();
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function ensureSession() {
      const stored = getAccessToken();
      if (stored) {
        setTokens(stored);
      }

      const hasSessionHint = !!useAuthStore.getState().user || !!getAccessToken();
      if (hasSessionHint) {
        const token = await bootstrapAuthSession();
        if (cancelled) return;
        if (token) {
          setTokens(token);
          setAuthReady(true);
          return;
        }
        logout();
        router.replace("/login?session=expired");
        return;
      }

      if (!isAuthenticated()) {
        router.replace("/login");
        return;
      }
      if (!cancelled) setAuthReady(true);
    }

    const run = () => {
      void ensureSession();
    };

    if (useAuthStore.persist.hasHydrated()) {
      run();
    } else {
      const unsub = useAuthStore.persist.onFinishHydration(() => {
        unsub();
        run();
      });
      return () => {
        cancelled = true;
        unsub();
      };
    }

    return () => {
      cancelled = true;
    };
  }, [setTokens, logout, isAuthenticated, router]);

  if (!authReady) {
    return (
      <div className="min-h-screen flex items-center justify-center text-cyber-muted text-sm">
        Restaurando sesión…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <header className="h-14 border-b border-cyber-border flex items-center justify-between px-6 bg-cyber-surface/50 backdrop-blur">
          <h2 className="text-sm font-medium text-cyber-muted">Security Operations Center</h2>
          <div className="flex items-center gap-3 text-sm">
            <ThemeToggle />
            {connected ? (
              <>
                <Wifi size={16} className="text-cyber-accent" />
                <span className="text-cyber-accent">Live</span>
              </>
            ) : (
              <>
                <WifiOff size={16} className="text-cyber-muted" />
                <span className="text-cyber-muted">Reconnecting...</span>
              </>
            )}
          </div>
        </header>
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
