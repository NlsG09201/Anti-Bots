"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { useAuthStore } from "@/stores/authStore";
import { useWebSocketContext } from "@/contexts/WebSocketContext";
import { Wifi, WifiOff } from "lucide-react";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const { connected } = useWebSocketContext();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
    }
  }, [isAuthenticated, router]);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <header className="h-14 border-b border-cyber-border flex items-center justify-between px-6 bg-cyber-surface/50 backdrop-blur">
          <h2 className="text-sm font-medium text-cyber-muted">Security Operations Center</h2>
          <div className="flex items-center gap-2 text-sm">
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
