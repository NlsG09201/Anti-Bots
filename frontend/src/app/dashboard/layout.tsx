"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Menu, Wifi, WifiOff } from "lucide-react";
import { Sidebar, getDashboardPageTitle } from "@/components/Sidebar";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useWebSocketContext } from "@/contexts/WebSocketContext";
import { bootstrapAuthSession, fetchCsrfToken, getAccessToken } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { setTokens, logout } = useAuthStore();
  const { connected } = useWebSocketContext();
  const [authReady, setAuthReady] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function ensureSession() {
      const stored = getAccessToken();
      if (stored) setTokens(stored);

      const hasSessionHint = !!useAuthStore.getState().user || !!getAccessToken();
      if (!hasSessionHint) {
        router.replace("/login");
        return;
      }

      const token = await bootstrapAuthSession();
      if (cancelled) return;
      if (token) {
        setTokens(token);
        await fetchCsrfToken();
        setAuthReady(true);
        return;
      }

      logout();
      router.replace("/login?session=expired");
    }

    const run = () => void ensureSession();
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
  }, [setTokens, logout, router]);

  if (!authReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-cyber-bg text-sm text-cyber-muted" role="status" aria-live="polite">
        Restoring your session...
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-cyber-bg">
      <Sidebar mobileOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-[4.5rem] shrink-0 items-center justify-between border-b border-cyber-border bg-cyber-bg/90 px-4 backdrop-blur-xl sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              aria-label="Open main navigation"
              aria-controls="primary-navigation"
              aria-expanded={mobileNavOpen}
              onClick={() => setMobileNavOpen(true)}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-cyber-border bg-cyber-surface text-cyber-muted hover:text-cyber-text md:hidden"
            >
              <Menu size={18} />
            </button>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-cyber-text">{getDashboardPageTitle(pathname)}</p>
              <p className="hidden text-[11px] text-cyber-muted sm:block">Security workspace</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-4">
            <ThemeToggle />
            <span className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-cyber-border bg-cyber-surface px-2.5 text-xs font-medium text-cyber-muted sm:px-3" role="status" aria-live="polite">
              {connected ? <Wifi size={14} className="text-cyber-accent" /> : <WifiOff size={14} />}
              <span className="hidden sm:inline">{connected ? "Live updates" : "Reconnecting"}</span>
              <span className="sm:hidden">{connected ? "Live" : "Offline"}</span>
            </span>
          </div>
        </header>
        <main id="main-content" className="w-full flex-1 p-4 sm:p-6 xl:p-8">
          <div className="mx-auto w-full max-w-[1600px]">{children}</div>
        </main>
      </div>
    </div>
  );
}
