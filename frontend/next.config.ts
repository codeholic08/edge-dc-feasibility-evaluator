import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /** Proxy API to FastAPI during local dev (optional; frontend also reads NEXT_PUBLIC_API_URL). */
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/backend/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
