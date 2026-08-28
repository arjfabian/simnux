#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/deploy-backend-to-flyio.sh"
"$SCRIPT_DIR/deploy-frontend-to-flyio.sh"
