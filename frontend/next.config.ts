import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL || "http://localhost:8001"}/api/:path*`,
      },
    ];
  },
  experimental: {
    proxyTimeout: 120000, // 120s — LLM calls can take 60+ seconds
  },
};

export default nextConfig;
