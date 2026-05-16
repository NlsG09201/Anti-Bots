/** @type {import('next').NextConfig} */
const publicApi = process.env.NEXT_PUBLIC_API_URL || "";
const apiTarget =
  process.env.API_PROXY_TARGET ||
  (publicApi && !/localhost|127\.0\.0\.1/i.test(publicApi) ? publicApi : "") ||
  "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget.replace(/\/$/, "")}/api/:path*`,
      },
    ];
  },
  // Logging para debug
  onDemandEntries: {
    maxInactiveAge: 60 * 1000,
    pagesBufferLength: 5,
  },
};

module.exports = nextConfig;
