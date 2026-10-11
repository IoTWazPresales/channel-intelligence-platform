/**
 * Dev API listen address. Default is IPv4 loopback so pnpm dev:api is not LAN-visible.
 * CIP_API_HOST overrides (including a non-loopback host); empty falls back to the default.
 */
const DEFAULT_API_HOST = '127.0.0.1';

function resolveApiBindHost(env) {
  const raw = env && env.CIP_API_HOST;
  const trimmed = typeof raw === 'string' ? raw.trim() : '';
  return trimmed || DEFAULT_API_HOST;
}

function isLoopbackHost(host) {
  const h = String(host || '').trim().toLowerCase();
  return h === '127.0.0.1' || h === '::1' || h === 'localhost';
}

module.exports = { DEFAULT_API_HOST, resolveApiBindHost, isLoopbackHost };
