import Link from "next/link";
import {
  Activity, ArrowDownRight, ArrowRight, Eye, Fingerprint, RadioTower, ShieldCheck,
} from "lucide-react";

const platforms = ["Twitch", "Kick", "YouTube Live", "TikTok Live"];

const capabilities = [
  {
    icon: Activity,
    title: "Monitor live activity",
    description: "Follow channel health, viewer signals, and moderation events from one workspace.",
  },
  {
    icon: Fingerprint,
    title: "Investigate suspicious patterns",
    description: "Review threat signals, suspicious viewers, and incident history with context.",
  },
  {
    icon: Eye,
    title: "Keep moderation understandable",
    description: "See alerts and detection evidence before choosing how your channel responds.",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen overflow-hidden bg-cyber-bg text-cyber-text">
      <a href="#main-content" className="sr-only z-50 rounded-md bg-cyber-surface px-4 py-2 focus:not-sr-only focus:fixed focus:left-4 focus:top-4">
        Skip to content
      </a>

      <header className="relative z-10 border-b border-cyber-border/70">
        <nav aria-label="Main navigation" className="mx-auto flex h-[4.5rem] max-w-7xl items-center justify-between px-5 sm:px-8">
          <Link href="/" className="flex items-center gap-3 rounded-md focus-visible:outline-none">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-cyber-accent/10 text-cyber-accent ring-1 ring-inset ring-cyber-accent/20">
              <ShieldCheck size={19} />
            </span>
            <span className="text-sm font-semibold tracking-tight sm:text-base">Anti-Bots <span className="text-cyber-accent">AI</span></span>
          </Link>
          <div className="hidden items-center gap-8 text-sm text-cyber-muted md:flex">
            <a href="#protection" className="transition-colors hover:text-cyber-text">Protection</a>
            <a href="#platforms" className="transition-colors hover:text-cyber-text">Platforms</a>
            <a href="#workflow" className="transition-colors hover:text-cyber-text">How it works</a>
          </div>
          <Link href="/login" className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-cyber-border bg-cyber-surface px-4 text-sm font-semibold transition-colors hover:border-cyber-accent/50 hover:text-cyber-accent">
            Sign in <ArrowRight size={15} />
          </Link>
        </nav>
      </header>

      <section id="main-content" className="relative isolate">
        <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[34rem] bg-[radial-gradient(ellipse_70%_60%_at_50%_0%,rgb(var(--cyber-accent-rgb)_/_0.12),transparent)]" />
        <div className="mx-auto grid max-w-7xl items-center gap-14 px-5 pb-20 pt-20 sm:px-8 sm:pb-28 sm:pt-28 lg:grid-cols-[1.05fr_0.95fr] lg:gap-20">
          <div>
            <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-cyber-border bg-cyber-surface/80 px-3 py-1.5 text-xs font-medium text-cyber-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-cyber-accent" />
              Security visibility for live communities
            </div>
            <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">
              Protect your live community with <span className="text-cyber-accent">clearer signals.</span>
            </h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-cyber-muted sm:text-lg">
              Bring channel activity, suspicious viewer signals, and moderation alerts into one security workspace built for streamers and their teams.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link href="/login" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-cyber-accent px-5 text-sm font-semibold text-cyber-on-accent transition-colors hover:bg-cyber-accent/90">
                Open your workspace <ArrowRight size={16} />
              </Link>
              <a href="#protection" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border border-cyber-border bg-cyber-surface/70 px-5 text-sm font-semibold transition-colors hover:border-cyber-muted/60">
                Explore protection <ArrowDownRight size={16} />
              </a>
            </div>
            <p className="mt-4 text-xs leading-5 text-cyber-muted">Monitoring availability varies by platform connection and enabled integrations.</p>
          </div>

          <div className="relative mx-auto w-full max-w-xl">
            <div aria-hidden="true" className="absolute -inset-8 -z-10 rounded-full bg-cyber-info/10 blur-3xl" />
            <div className="rounded-2xl border border-cyber-border bg-cyber-surface/90 p-5 shadow-2xl shadow-black/20 sm:p-7">
              <div className="flex items-center justify-between border-b border-cyber-border px-1 pb-4">
                <div>
                  <p className="text-xs font-semibold text-cyber-text">Security workspace</p>
                  <p className="mt-1 text-[11px] text-cyber-muted">Your channels, signals, and response tools</p>
                </div>
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-cyber-accent/10 text-cyber-accent">
                  <RadioTower size={18} />
                </span>
              </div>
              <div className="relative grid gap-3 py-6 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
                <div className="space-y-3">
                  <div className="flex items-center gap-3 rounded-xl border border-cyber-border bg-cyber-bg/70 p-3.5">
                    <Activity size={17} className="text-cyber-accent" />
                    <span><span className="block text-xs font-semibold">Monitor</span><span className="mt-0.5 block text-[10px] text-cyber-muted">Channel activity and health</span></span>
                  </div>
                  <div className="flex items-center gap-3 rounded-xl border border-cyber-border bg-cyber-bg/70 p-3.5">
                    <Fingerprint size={17} className="text-cyber-info" />
                    <span><span className="block text-xs font-semibold">Investigate</span><span className="mt-0.5 block text-[10px] text-cyber-muted">Threat signals and incidents</span></span>
                  </div>
                </div>
                <div aria-hidden="true" className="hidden h-px w-8 bg-cyber-border sm:block" />
                <div className="flex items-center gap-3 rounded-xl border border-cyber-accent/25 bg-cyber-accent/5 p-4 sm:min-h-28 sm:flex-col sm:items-start sm:justify-center">
                  <ShieldCheck size={20} className="shrink-0 text-cyber-accent" />
                  <span><span className="block text-xs font-semibold">Review</span><span className="mt-1 block text-[10px] leading-4 text-cyber-muted">See moderation alerts and choose the next action.</span></span>
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-cyber-border pt-4">
                <span className="text-[11px] text-cyber-muted">Reviewable signals. Your account data.</span>
                <Link href="/login" className="text-xs font-semibold text-cyber-accent hover:underline">View workspace <ArrowRight size={13} className="ml-1 inline" /></Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="platforms" className="border-y border-cyber-border/70 bg-cyber-surface/40">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-7 sm:px-8 md:flex-row md:items-center md:justify-between">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-cyber-muted">Platform workflows in the product</p>
          <ul className="flex flex-wrap gap-2" aria-label="Supported streaming platforms">
            {platforms.map((platform) => <li key={platform} className="rounded-full border border-cyber-border bg-cyber-bg px-3 py-1.5 text-xs font-medium text-cyber-text">{platform}</li>)}
          </ul>
        </div>
      </section>

      <section id="protection" className="mx-auto max-w-7xl px-5 py-20 sm:px-8 sm:py-24">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-cyber-accent">Protection, with context</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Know what needs attention.</h2>
          <p className="mt-4 text-sm leading-6 text-cyber-muted sm:text-base">Bring monitoring, investigation, and moderation review together without hiding the evidence behind a score.</p>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {capabilities.map(({ icon: Icon, title, description }, index) => (
            <article key={title} className="rounded-xl border border-cyber-border bg-cyber-surface p-6 transition-colors hover:border-cyber-accent/35">
              <span className="grid h-10 w-10 place-items-center rounded-lg bg-cyber-surface-elevated text-cyber-accent"><Icon size={19} /></span>
              <p className="mt-5 text-xs font-medium text-cyber-muted">0{index + 1}</p>
              <h3 className="mt-1 text-base font-semibold text-cyber-text">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-cyber-muted">{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="workflow" className="border-y border-cyber-border/70 bg-cyber-surface/40">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-16 sm:px-8 sm:py-20 lg:grid-cols-[0.8fr_1.2fr] lg:items-center">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-cyber-accent">A clear starting point</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight">From connection to review.</h2>
            <p className="mt-4 text-sm leading-6 text-cyber-muted">Start with a channel, choose the protection settings your team needs, and monitor the resulting activity.</p>
            <Link href="/login" className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-lg border border-cyber-border bg-cyber-surface px-4 text-sm font-semibold hover:border-cyber-accent/50 hover:text-cyber-accent">
              Get started <ArrowRight size={15} />
            </Link>
          </div>
          <ol className="grid gap-3 sm:grid-cols-3">
            {[
              ["Connect", "Link a channel using the platform flow available to your account."],
              ["Configure", "Review monitoring and moderation options for that channel."],
              ["Monitor", "Use alerts and activity views to investigate what needs attention."],
            ].map(([title, description], index) => (
              <li key={title} className="rounded-xl border border-cyber-border bg-cyber-surface p-5">
                <span className="text-xs font-semibold text-cyber-accent">STEP 0{index + 1}</span>
                <h3 className="mt-4 text-sm font-semibold">{title}</h3>
                <p className="mt-2 text-xs leading-5 text-cyber-muted">{description}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <footer className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-8 text-xs text-cyber-muted sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <p>Anti-Bots AI · Security visibility for live communities</p>
        <Link href="/login" className="font-medium hover:text-cyber-accent">Sign in to your workspace</Link>
      </footer>
    </main>
  );
}
