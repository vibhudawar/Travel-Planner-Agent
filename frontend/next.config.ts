import type { NextConfig } from "next"

// Pin the workspace root to this app so Next doesn't infer a parent lockfile.
const nextConfig: NextConfig = {
  turbopack: { root: import.meta.dirname },
}

export default nextConfig
