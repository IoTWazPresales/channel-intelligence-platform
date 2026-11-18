// ESLint 9 flat config (BACKLOG-231). Same rule set as the legacy `eslintConfig` block it replaces:
// eslint-config-next 15 `next/core-web-vitals` through FlatCompat. No new rules here; the existing
// warnings (react-hooks/exhaustive-deps) are the recorded baseline, not fixed in this change.
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { FlatCompat } from '@eslint/eslintrc';

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  { ignores: ['.next/**', 'node_modules/**', 'playwright-report/**', 'test-results/**'] },
  ...compat.extends('next/core-web-vitals'),
];

export default config;