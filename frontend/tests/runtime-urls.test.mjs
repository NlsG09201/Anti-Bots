import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import runtimeUrls from "../.test-build/runtime-urls.js";
import platformBadgeModule from "../.test-build/components/PlatformBadge.js";
import statCardModule from "../.test-build/components/StatCard.js";
import lucideModule from "lucide-react";

const { PlatformBadge } = platformBadgeModule;
const { StatCard } = statCardModule;
const { Shield } = lucideModule;

const originalWindow = globalThis.window;
const originalEnv = {
  api: process.env.NEXT_PUBLIC_API_URL,
  directApi: process.env.NEXT_PUBLIC_API_DIRECT_URL,
  websocket: process.env.NEXT_PUBLIC_WS_URL,
};

afterEach(() => {
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
  for (const [name, value] of [
    ["NEXT_PUBLIC_API_URL", originalEnv.api],
    ["NEXT_PUBLIC_API_DIRECT_URL", originalEnv.directApi],
    ["NEXT_PUBLIC_WS_URL", originalEnv.websocket],
  ]) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
});

test("production browser uses same-origin proxy for cookie-backed API calls", () => {
  globalThis.window = { location: { hostname: "anti-bots.vercel.app", origin: "https://anti-bots.vercel.app" } };
  process.env.NEXT_PUBLIC_API_URL = "https://api.example.test/";

  assert.equal(runtimeUrls.resolveApiBaseUrl(), "");
});

test("production direct API calls use the configured API host", () => {
  globalThis.window = { location: { hostname: "anti-bots.vercel.app", origin: "https://anti-bots.vercel.app" } };
  process.env.NEXT_PUBLIC_API_URL = "https://api.example.test/";
  process.env.NEXT_PUBLIC_API_DIRECT_URL = "https://api.example.test/";

  assert.equal(runtimeUrls.resolveDirectApiBaseUrl(), "https://api.example.test");
});

test("local development keeps configured API and websocket endpoints", () => {
  globalThis.window = { location: { hostname: "localhost", origin: "http://localhost:3000" } };
  process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000/";
  process.env.NEXT_PUBLIC_WS_URL = "ws://localhost:8000/";

  assert.equal(runtimeUrls.resolveApiBaseUrl(), "http://localhost:8000");
  assert.equal(runtimeUrls.resolveWsBaseUrl(), "ws://localhost:8000");
});

test("production ignores localhost build-time API and websocket values", () => {
  globalThis.window = { location: { hostname: "anti-bots.vercel.app", origin: "https://anti-bots.vercel.app" } };
  process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
  process.env.NEXT_PUBLIC_WS_URL = "ws://localhost:8000";

  assert.equal(runtimeUrls.resolveApiBaseUrl(), "");
  assert.equal(runtimeUrls.resolveWsBaseUrl(), "");
});

test("platform badge renders provider labels and safely falls back for unknown values", () => {
  const kick = renderToStaticMarkup(createElement(PlatformBadge, { platform: "KICK" }));
  const unknown = renderToStaticMarkup(createElement(PlatformBadge, { platform: "other" }));

  assert.match(kick, />Kick</);
  assert.match(unknown, />Other</);
});

test("stat card renders its value, optional trend, and selected severity style", () => {
  const markup = renderToStaticMarkup(
    createElement(StatCard, {
      title: "Suspicious users",
      value: 0,
      icon: Shield,
      trend: "No new detections",
      variant: "warning",
    }),
  );

  assert.match(markup, />Suspicious users</);
  assert.match(markup, />0</);
  assert.match(markup, />No new detections</);
  assert.match(markup, /border-cyber-warning\/30/);
});
