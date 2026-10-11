import { isIP } from 'node:net';

/**
 * Client-address headers for the same-origin API proxy (N-0086).
 *
 * Trust model (see .eif/audit/PROGRAMME_20261009/N0086_IMPL.md, decision on client-IP trust):
 * - The production web listens on 127.0.0.1 only (scripts/cip-supervisor.ps1 starts `next start -H 127.0.0.1`
 *   and replaces any wider listener). So every TCP peer is either cloudflared (the quick tunnel connects to
 *   127.0.0.1:3000) or a process on this machine.
 * - For tunnel traffic, Cloudflare's edge sets `CF-Connecting-IP` to the visitor's address and overwrites any
 *   value the visitor sent; cloudflared relays it. That is the only client address we trust.
 * - With no valid `CF-Connecting-IP`, the request came from this machine (or, if someone binds the web wider,
 *   from a network peer we cannot see from a route handler). It is keyed as loopback. Visitor-supplied
 *   `X-Forwarded-For` / `X-Real-IP` / `Forwarded` are never trusted: Next 15 only fills `X-Forwarded-For` when
 *   the client did not send one, so its value can be chosen by the client.
 * - A local process can forge `CF-Connecting-IP`, but it can already reach the API on 127.0.0.1:8001
 *   directly, so that is not a new capability.
 *
 * The proxy drops every incoming client-address header and sends exactly one address upstream in
 * `X-Forwarded-For` and `X-Real-IP`. The API honours `X-Forwarded-For` only from a loopback peer.
 */

/** Key used when the request did not come through the Cloudflare tunnel. */
export const LOCAL_CLIENT_ADDRESS = '127.0.0.1';

/** Incoming headers that name a client address. All are removed before forwarding. */
export const CLIENT_ADDRESS_HEADERS = [
  'x-forwarded-for',
  'x-real-ip',
  'forwarded',
  'cf-connecting-ip',
  'cf-connecting-ipv6',
  'true-client-ip',
  'x-client-ip',
  'x-cluster-client-ip',
] as const;

/** Headers that must not be copied hop to hop (plus `host`, which fetch sets for the upstream). */
export const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailers',
  'transfer-encoding',
  'upgrade',
  'host',
]);

const DROP = new Set<string>([...HOP_BY_HOP, ...CLIENT_ADDRESS_HEADERS]);

/** A single IPv4 or IPv6 literal, or null. Rejects lists, ports, brackets and anything else. */
export function parseIpLiteral(raw: string | null | undefined): string | null {
  if (raw == null) return null;
  const v = raw.trim();
  if (!v || v.length > 64) return null;
  return isIP(v) ? v.toLowerCase() : null;
}

/** The client address the proxy trusts for this request (see the trust model above). */
export function resolveClientAddress(incoming: Headers): string {
  return parseIpLiteral(incoming.get('cf-connecting-ip')) ?? LOCAL_CLIENT_ADDRESS;
}

/**
 * Headers to send upstream: the incoming headers minus hop-by-hop and every client-address header,
 * plus one trusted address in `X-Forwarded-For` and `X-Real-IP`.
 */
export function buildUpstreamHeaders(incoming: Headers): Headers {
  const out = new Headers();
  incoming.forEach((value, key) => {
    if (!DROP.has(key.toLowerCase())) out.set(key, value);
  });
  const address = resolveClientAddress(incoming);
  out.set('x-forwarded-for', address);
  out.set('x-real-ip', address);
  return out;
}
