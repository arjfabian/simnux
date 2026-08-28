#!/usr/bin/env bash

set -euo pipefail

# Color indicators for build status
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Collect the Fly app names (mandatory). The user supplies the domain only;
# the ".fly.dev" suffix is appended here so cloners can't hit the author's URLs.
BACKEND_DOMAIN=""
while [ -z "$BACKEND_DOMAIN" ]; do
    read -r -p "Backend app domain (no scheme, no .fly.dev): " BACKEND_DOMAIN
done

# The backend's CORS allow-list must match the frontend origin, so we need the
# frontend domain too.
FRONTEND_DOMAIN=""
while [ -z "$FRONTEND_DOMAIN" ]; do
    read -r -p "Frontend app domain (no scheme, no .fly.dev): " FRONTEND_DOMAIN
done

BACKEND_URL="https://${BACKEND_DOMAIN}.fly.dev"
FRONTEND_URL="https://${FRONTEND_DOMAIN}.fly.dev"

# Rewrite backend/fly.toml in place so the app name and CORS origin match.
sed -i -E "s#^app = .*#app = \"$BACKEND_DOMAIN\"#" backend/fly.toml
sed -i -E "s#^[[:space:]]*ALLOWED_ORIGINS = .*#  ALLOWED_ORIGINS = \"$FRONTEND_URL\"#" backend/fly.toml

echo -e "${BLUE}==> Deploying SIMNUX Backend (${BACKEND_DOMAIN})...${NC}"
(cd backend && fly deploy)

echo -e "\n${GREEN}==> Backend deployed successfully!${NC}"
echo "Backend: ${BACKEND_URL}"
