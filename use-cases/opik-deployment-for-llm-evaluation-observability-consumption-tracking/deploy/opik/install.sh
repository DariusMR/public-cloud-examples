#!/usr/bin/env bash
set -euo pipefail

helm repo add opik https://comet-ml.github.io/opik/
helm repo update opik

OPIK_CHART_VERSION="2.2.12"

# altinity CRDs: helm only applies crds/ on install, never on upgrade.
if ! kubectl get crd clickhouseinstallations.clickhouse.altinity.com >/dev/null 2>&1; then
  echo "Altinity operator CRDs missing, installing..."
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  helm pull opik/opik --version "$OPIK_CHART_VERSION" --untar --untardir "$tmp"
  kubectl apply --server-side -f "$tmp/opik/charts/altinity-clickhouse-operator/crds"
fi

helm upgrade --install opik \
  opik/opik \
  --version "$OPIK_CHART_VERSION" \
  -n opik \
  -f deploy/opik/values.yaml \
  --wait --timeout 10m
