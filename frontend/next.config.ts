import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // The backend already serves sized WebP thumbnails / JPEG previews.
  images: { unoptimized: true },
};

export default nextConfig;
