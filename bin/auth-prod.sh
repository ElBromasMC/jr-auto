#!/bin/sh

exec docker compose -f docker-compose.yml \
    run -it --rm \
    jr-auto /home/runner/docker-authenticate-prod.sh

