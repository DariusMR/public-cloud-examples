#!/usr/bin/env bash
set -euo pipefail

CERT_MANAGER_CHART_VERSION="v1.19.1"

# one nodeSelector per component, top-level key only covers the controller
helm upgrade --install cert-manager \
  oci://quay.io/jetstack/charts/cert-manager \
  --version "$CERT_MANAGER_CHART_VERSION" \
  -n cert-manager \
  --create-namespace \
  --set crds.enabled=true \
  --set nodeSelector.nodepool=np-system \
  --set webhook.nodeSelector.nodepool=np-system \
  --set cainjector.nodeSelector.nodepool=np-system \
  --set startupapicheck.nodeSelector.nodepool=np-system \
  --wait --timeout 5m
