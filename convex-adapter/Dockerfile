FROM node:24-alpine AS build
COPY --from=oven/bun:1.3.14 /usr/local/bin/bun /usr/local/bin/bun

WORKDIR /app

COPY package.json bun.lock bunfig.toml ./
COPY frontend/package.json ./frontend/package.json
COPY convex-adapter/package.json ./convex-adapter/package.json
RUN bun install --frozen-lockfile

COPY convex-adapter/src ./convex-adapter/src
COPY convex-adapter/tsconfig.json ./convex-adapter/tsconfig.json
RUN bun run build:adapter


FROM node:24-alpine AS runtime
COPY --from=oven/bun:1.3.14 /usr/local/bin/bun /usr/local/bin/bun

ENV NODE_ENV=production

WORKDIR /app

COPY package.json bun.lock bunfig.toml ./
COPY frontend/package.json ./frontend/package.json
COPY convex-adapter/package.json ./convex-adapter/package.json
RUN bun install --frozen-lockfile --production --filter supportoid-convex-adapter

COPY --from=build /app/convex-adapter/dist ./convex-adapter/dist
RUN mkdir -p /app/data && chown node:node /app/data

USER node

EXPOSE 4010

CMD ["node", "convex-adapter/dist/index.js"]
