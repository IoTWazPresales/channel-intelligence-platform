import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  transpilePackages: ['@cip/ui', '@cip/types'],
  /**
   * Same-origin `/api/v1/...` in dev is handled by `src/app/api/v1/[[...path]]/route.ts` (server proxy),
   * which is more reliable here than `rewrites()` with the App Router.
   */
};

export default nextConfig;
