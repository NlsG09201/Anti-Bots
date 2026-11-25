import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Anti-Bots AI | Seguridad para directos",
  description: "Detecta actividad sospechosa y revisa alertas de moderación en tus canales en vivo.",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="dark" suppressHydrationWarning>
      <body className="min-h-screen bg-cyber-bg antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
