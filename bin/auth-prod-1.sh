#!/bin/bash

SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"

echo "### Script executed at: $(date '+%Y-%m-%d %H:%M:%S')"
"${PROJECT_ROOT}/bin/compose-prod-1.sh" run --rm jr-auto /home/runner/docker-authenticate-prod.sh

