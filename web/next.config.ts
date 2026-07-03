import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output: consumed by the deploy Dockerfile (P5).
  output: "standalone",
};

export default nextConfig;
