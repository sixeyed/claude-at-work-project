# syntax=docker/dockerfile:1
# CollabHub SPA. Node is build-time only; the runtime is Nginx serving static
# files (docs/platform/versions.md, nodejs + nginx entries).

FROM node:24-slim AS builder

WORKDIR /app
COPY src/frontend/package.json src/frontend/package-lock.json* ./
RUN npm install

COPY src/frontend/ ./

# Vite inlines VITE_-prefixed vars at build time, so they are build args rather
# than runtime env. Only non-secret values belong here — they ship in the bundle.
ARG VITE_AUTH_URL
ARG VITE_MESSAGING_URL
ARG VITE_CANVAS_URL
ARG VITE_ASSET_URL

RUN npm run build

FROM nginx:1.30-alpine

# SPA routing: unknown paths fall through to index.html rather than 404.
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
