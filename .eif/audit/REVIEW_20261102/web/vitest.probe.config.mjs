// GOV-008 review probe config (2026-11-02). Run from apps/web so root = apps/web; the probe test lives
// outside product source, so bare imports it makes are aliased to apps/web/node_modules. No product file changes.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(process.cwd());
const nm = (p) => path.join(web, 'node_modules', p);

export default {
  esbuild: { jsx: 'automatic' },
  resolve: {
    alias: [
      { find: '@', replacement: path.join(web, 'src') },
      { find: /^react$/, replacement: nm('react') },
      { find: /^react\/(.*)$/, replacement: nm('react') + '/$1' },
      { find: /^@testing-library\/react$/, replacement: nm('@testing-library/react') },
      { find: /^recharts$/, replacement: nm('recharts') },
    ],
  },
  test: {
    root: web,
    dir: here,
    environment: 'jsdom',
    globals: true,
    setupFiles: [path.join(web, 'vitest.setup.ts')],
    include: ['**/*.probe.test.tsx'],
    testTimeout: 15000,
  },
};
