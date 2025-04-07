#!/bin/sh

COMPOSE_PROVIDER="${COMPOSE_PROVIDER:-docker compose}"

exec ${COMPOSE_PROVIDER} -f docker-compose.dev.yml run --rm --build devrunner

