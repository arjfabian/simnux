#!/bin/sh
# Generate frontend/config.js from config.js.template, substituting the
# backend URL from the SIMNUX_BACKEND_URL environment variable. Defaults to
# the local development backend (http://127.0.0.1:8000).
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEMPLATE="$SCRIPT_DIR/config.js.template"
OUTPUT="$SCRIPT_DIR/config.js"

: "${SIMNUX_BACKEND_URL:=http://127.0.0.1:8000}"

if [ ! -r "$TEMPLATE" ]; then
    echo "build.sh: cannot read template: $TEMPLATE" >&2
    exit 1
fi

sed "s|\${SIMNUX_BACKEND_URL}|${SIMNUX_BACKEND_URL}|g" "$TEMPLATE" > "$OUTPUT"

echo "Generated $OUTPUT (BACKEND_URL=${SIMNUX_BACKEND_URL})"