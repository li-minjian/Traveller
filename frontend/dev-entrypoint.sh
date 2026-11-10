#!/bin/sh
# Development container: node_modules lives in a Docker volume. Reinstall the
# dependencies when package-lock.json changed since the last install, then
# start the given command (the Vite dev server).
set -e
marker=node_modules/.package-lock.sha256
if ! sha256sum -c "$marker" >/dev/null 2>&1; then
  echo "package-lock.json changed - installing dependencies"
  npm ci --no-audit --no-fund
  sha256sum package-lock.json > "$marker"
fi
exec "$@"
