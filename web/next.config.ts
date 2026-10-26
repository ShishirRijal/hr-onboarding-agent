import type { NextConfig } from "next";

// The browser talks to /api/*, which Next proxies to the FastAPI backend,
// so the web app and API share an origin (no CORS, and auth cookies work later).
const apiUrl = process.env.HR_API_URL ?? "http://localhost:8010";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
