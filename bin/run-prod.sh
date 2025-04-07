#!/bin/sh

COMPOSE_PROVIDER="${COMPOSE_PROVIDER:-docker compose}"

exec ${COMPOSE_PROVIDER} -f docker-compose.yml run -T --rm jr-auto

