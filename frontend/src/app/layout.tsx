import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Anti-Bots AI | StreamShield Security",
  description: "Monitor suspicious activity and moderation signals across your live streaming channels.",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
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
