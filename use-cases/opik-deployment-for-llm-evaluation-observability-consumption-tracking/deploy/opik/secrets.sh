#!/usr/bin/env bash
set -euo pipefail

# REDIS_URL is rewritten to rediss:// - redis-py rejects the valkeys:// the control panel shows

NS="${NS:-opik}"

current() {
  kubectl -n "$NS" get secret opik-secrets -o "jsonpath={.data.$1}" 2>/dev/null \
    | base64 -d 2>/dev/null || true
}

# env var wins over the existing secret value
resolve() {
  local key="$1" override="${2-}" value
  value="${override:-$(current "$key")}"
  [ -n "$value" ] || {
    echo "Missing value for $key, and not found in the existing secret either." >&2
    exit 1
  }
  printf '%s' "$value"
}

STATE_DB_PASS="$(resolve STATE_DB_PASS "${MYSQL_PASSWORD-}")"
ANALYTICS_DB_PASS="$(resolve ANALYTICS_DB_PASS "${CLICKHOUSE_PASSWORD-}")"
# AWS_* names are the chart's own naming - these actually hold your OVHcloud S3 credentials.
AWS_ACCESS_KEY_ID="$(resolve AWS_ACCESS_KEY_ID "${S3_ACCESS_KEY-}")"
AWS_SECRET_ACCESS_KEY="$(resolve AWS_SECRET_ACCESS_KEY "${S3_SECRET_KEY-}")"

if [ -n "${VALKEY_PASSWORD-}" ]; then
  VALKEY_HOST="${VALKEY_HOST:?set VALKEY_HOST, e.g. valkey-xxxxxxxx-xxxxxxxx.database.cloud.ovh.net}"
  VALKEY_PORT="${VALKEY_PORT:-20185}"
  REDIS_URL="rediss://default:${VALKEY_PASSWORD}@${VALKEY_HOST}:${VALKEY_PORT}/0"
else
  REDIS_URL="$(resolve REDIS_URL)"
fi

kubectl -n "$NS" create secret generic opik-secrets \
  --from-literal=STATE_DB_PASS="${STATE_DB_PASS}" \
  --from-literal=ANALYTICS_DB_PASS="${ANALYTICS_DB_PASS}" \
  --from-literal=ANALYTICS_DB_MIGRATIONS_PASS="${ANALYTICS_DB_PASS}" \
  --from-literal=REDIS_URL="${REDIS_URL}" \
  --from-literal=AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
  --from-literal=AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
  --dry-run=client -o yaml | kubectl apply -f -

# pods read this via envFrom, so they won't see new values until restarted
echo "opik-secrets updated. To apply:" >&2
echo "  kubectl rollout restart -n $NS deploy/opik-backend deploy/opik-python-backend" >&2

# separate secret, read by the Traefik middleware - needs a `users` key

if [ -n "${UI_PASSWORD-}" ] || ! kubectl -n "$NS" get secret opik-ui-auth >/dev/null 2>&1; then
  UI_USER="${UI_USER:-admin}"

  if [ -z "${UI_PASSWORD-}" ]; then
    read -rsp "Password for Opik UI user '${UI_USER}': " UI_PASSWORD
    echo
  fi
  [ -n "${UI_PASSWORD}" ] || { echo "Empty password, aborting." >&2; exit 1; }

  command -v htpasswd >/dev/null 2>&1 || {
    echo "htpasswd not found (apache2-utils or httpd-tools package)." >&2
    echo "No fallback: openssl can't produce bcrypt hashes." >&2
    exit 1
  }

  umask 077
  htp="$(mktemp)"
  trap 'rm -f "$htp"' EXIT

  # -i keeps the password out of the process list; -B forces bcrypt
  printf '%s' "${UI_PASSWORD}" | htpasswd -niB "${UI_USER}" > "$htp"

  kubectl -n "$NS" create secret generic opik-ui-auth \
    --from-file=users="$htp" \
    --dry-run=client -o yaml | kubectl apply -f -
fi
