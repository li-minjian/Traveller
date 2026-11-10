# Development: Vite dev server with hot reload. Docker Compose builds this
# stage and mounts the source code into /app.
FROM node:24.22.2-alpine AS dev
WORKDIR /app
COPY dev-entrypoint.sh /usr/local/bin/dev-entrypoint
RUN chmod 755 /usr/local/bin/dev-entrypoint && chown node:node /app
USER node
COPY --chown=node:node package.json package-lock.json ./
RUN npm ci --no-audit --no-fund \
  && sha256sum package-lock.json > node_modules/.package-lock.sha256
COPY --chown=node:node . .
EXPOSE 3000
ENTRYPOINT ["dev-entrypoint"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000", "--strictPort"]

# Production: static build served by Nginx (default target of `docker build`).
FROM dev AS build
RUN npm run build

FROM nginx:1.30.6-alpine AS production
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
