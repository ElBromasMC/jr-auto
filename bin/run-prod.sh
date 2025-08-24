#!/bin/sh

COMPOSE_PROVIDER="${COMPOSE_PROVIDER:-docker compose}"

echo "### Script executed at: $(date '+%Y-%m-%d %H:%M:%S')"
exec ${COMPOSE_PROVIDER} -f docker-compose.yml run --rm jr-auto

