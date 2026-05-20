import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "StreamShield - Anti-Bot Security Platform",
  description: "Enterprise anti-bot protection for Twitch, Kick, and YouTube Live streamers",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="min-h-screen bg-cyber-bg antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
