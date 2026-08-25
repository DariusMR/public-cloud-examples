#!/usr/bin/env bash
set -euo pipefail

helm repo add traefik https://traefik.github.io/charts
helm repo update traefik

TRAEFIK_CHART_VERSION="41.0.1"

# comment out the redirection lines on a fresh deploy, until the first cert is issued
helm upgrade --install traefik \
  traefik/traefik \
  --version "$TRAEFIK_CHART_VERSION" \
  -n traefik \
  --create-namespace \
  --set nodeSelector.nodepool=np-system \
  --set ports.web.http.redirections.entryPoint.to=websecure \
  --set ports.web.http.redirections.entryPoint.scheme=https \
  --set ports.web.http.redirections.entryPoint.permanent=true \
  --wait --timeout 3m
