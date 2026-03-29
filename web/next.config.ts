import type { NextConfig } from "next";

const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
const isDev = process.env.NODE_ENV !== "production";

const nextConfig: NextConfig = {
	output: "standalone",
	async rewrites() {
		if (!backendUrl) {
			if (isDev) {
				console.warn(
					"[web] NEXT_PUBLIC_API_BASE_URL nao definido; rewrites /api/v1 ficam desabilitados. " +
						"No modo local sem NGINX, configure NEXT_PUBLIC_API_BASE_URL=http://localhost:8000.",
				);
			}
			return [];
		}

		return [
			{
				source: "/api/v1/:path*",
				destination: `${backendUrl}/api/v1/:path*`,
			},
		];
	},
};

export default nextConfig;
