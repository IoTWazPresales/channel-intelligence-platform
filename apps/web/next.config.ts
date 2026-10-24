import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Isolated browser verification must never replace the running web service's .next output.
  distDir: process.env.CIP_NEXT_DIST_DIR ?? '.next',
  typescript: { tsconfigPath: process.env.CIP_NEXT_TSCONFIG ?? 'tsconfig.json' },
  transpilePackages: ['@cip/ui', '@cip/types', 'react-grid-layout', 'echarts'],
  /**
   * Same-origin `/api/v1/...` in dev is handled by `src/app/api/v1/[[...path]]/route.ts` (server proxy),
   * which is more reliable here than `rewrites()` with the App Router.
   */
};

export default nextConfig;
