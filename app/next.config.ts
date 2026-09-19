import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // A lockfile above the repo root (unrelated to this project) makes
  // Next.js misdetect the workspace root -- pin it explicitly.
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;
