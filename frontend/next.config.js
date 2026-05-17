/** @type {import('next').NextConfig} */
const isVercel = process.env.VERCEL === "1";
const publicApi = process.env.NEXT_PUBLIC_API_URL || "";
const renderDefault = "https://anti-bots-api.onrender.com";

const apiTarget = (
  process.env.API_PROXY_TARGET ||
  (publicApi && !/localhost|127\.0\.0\.1/i.test(publicApi) ? publicApi : "") ||
  (isVercel ? renderDefault : "http://localhost:8000")
).replace(/\/$/, "");

if (isVercel) {
  console.log("[next.config] API proxy ->", apiTarget);
  if (!process.env.API_PROXY_TARGET) {
    console.warn(
      "[next.config] API_PROXY_TARGET no definida; usando",
      renderDefault,
      "- anade la variable en Vercel y redeploy.",
    );
  }
}

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
