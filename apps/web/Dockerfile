# Build from the monorepo root (required for @cip/ui and @cip/types).
# Example: docker compose -f infra/docker/docker-compose.yml build web

FROM node:22-alpine

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

WORKDIR /repo

COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY apps/web/package.json ./apps/web/
COPY packages/ui/package.json ./packages/ui/
COPY packages/types/package.json ./packages/types/

RUN pnpm install --frozen-lockfile

COPY apps/web ./apps/web
COPY packages/ui ./packages/ui
COPY packages/types ./packages/types

# No NEXT_PUBLIC_API_URL at build time → client uses same-origin `/api/v1` (proxied via CIP_ENABLE_NEXT_API_PROXY).
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN pnpm --filter @cip/web build

EXPOSE 3000

WORKDIR /repo
CMD ["pnpm", "--filter", "@cip/web", "start"]
