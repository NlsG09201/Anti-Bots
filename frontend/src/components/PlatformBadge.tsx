import clsx from "clsx";

const STYLES: Record<string, string> = {
  twitch: "bg-purple-500/20 text-purple-300 border-purple-500/40",
  kick: "bg-green-500/20 text-green-300 border-green-500/40",
  youtube: "bg-red-500/20 text-red-300 border-red-500/40",
  tiktok: "bg-pink-500/20 text-pink-300 border-pink-500/40",
};

export function PlatformBadge({ platform }: { platform: string }) {
  const key = (platform || "twitch").toLowerCase();
  const labels: Record<string, string> = {
    youtube: "YouTube",
    tiktok: "TikTok",
    kick: "Kick",
    twitch: "Twitch",
  };
  const label = labels[key] ?? key.charAt(0).toUpperCase() + key.slice(1);
  return (
    <span
      className={clsx(
        "inline-flex items-center px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide rounded border",
        STYLES[key] ?? STYLES.twitch,
      )}
    >
      {label}
    </span>
  );
}
