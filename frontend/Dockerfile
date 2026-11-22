# syntax=docker/dockerfile:1.7

FROM node:26.2.0-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# This is public browser configuration, not a secret. It must remain relative
# so the nginx reverse proxy can forward API requests on the same origin.
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime

USER root

# The unprivileged image runs as UID 101. Copy the configuration and static
# assets with that ownership so a local source mode such as 0600 cannot make
# nginx unreadable when the container starts.
COPY --chown=101:101 nginx.conf /etc/nginx/conf.d/default.conf
RUN chmod 0644 /etc/nginx/conf.d/default.conf
COPY --from=build --chown=101:101 /app/dist /usr/share/nginx/html

USER 101

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["wget", "-qO-", "http://127.0.0.1:8080/healthz"]
