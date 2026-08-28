#!/usr/bin/env bash

set -euo pipefail

# Color indicators for build status
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Collect the Fly app names (mandatory). The user supplies the domain only;
# the ".fly.dev" suffix is appended here so cloners can't hit the author's URLs.
FRONTEND_DOMAIN=""
while [ -z "$FRONTEND_DOMAIN" ]; do
    read -r -p "Frontend app domain (no scheme, no .fly.dev): " FRONTEND_DOMAIN
done

# The frontend points its BACKEND_URL at the backend app, so we need the
# backend domain too.
BACKEND_DOMAIN=""
while [ -z "$BACKEND_DOMAIN" ]; do
    read -r -p "Backend app domain (no scheme, no .fly.dev): " BACKEND_DOMAIN
done

BACKEND_URL="https://${BACKEND_DOMAIN}.fly.dev"
FRONTEND_URL="https://${FRONTEND_DOMAIN}.fly.dev"

# Rewrite frontend/fly.toml in place so the app name and backend URL match.
sed -i -E "s#^app = .*#app = \"$FRONTEND_DOMAIN\"#" frontend/fly.toml
sed -i -E "s#^[[:space:]]*BACKEND_URL = .*#    BACKEND_URL = \"$BACKEND_URL\"#" frontend/fly.toml

echo -e "${BLUE}==> Deploying SIMNUX Frontend (${FRONTEND_DOMAIN})...${NC}"
(cd frontend && fly deploy)

echo -e "\n${GREEN}==> Frontend deployed successfully!${NC}"
echo "Frontend: ${FRONTEND_URL}"
