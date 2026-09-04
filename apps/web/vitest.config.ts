import path from 'path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  esbuild: {
    jsx: 'automatic',
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', 'src/**/*.integration.test.{ts,tsx}'],
    passWithNoTests: false,
    // Default 5s is too tight on this machine under full-suite jsdom load.
    // Isolation is fine (~1.6–2.1s); the same tests hit 5s+ when 107 files share a run
    // (BACKLOG-162: AdminImportsPage; DsiCandidateStewardPanel resolve-product).
    // Config-level, not per-test: the defect is the runner budget, not one assertion.
    testTimeout: 15000,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
