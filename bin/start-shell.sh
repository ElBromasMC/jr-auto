#!/bin/sh

exec docker compose -f docker-compose.dev.yml \
    run -it --rm --build --remove-orphans \
    devrunner /bin/bash

