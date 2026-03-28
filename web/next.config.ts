import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backendUrl =
      process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
      {
        source: "/jobs",
        destination: `${backendUrl}/api/v1/jobs`,
      },
    ];
  },
};

export default nextConfig;
