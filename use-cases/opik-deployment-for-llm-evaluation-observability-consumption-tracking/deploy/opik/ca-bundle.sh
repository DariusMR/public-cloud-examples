#!/usr/bin/env bash
set -euo pipefail

# bundles managed services' CAs into values.yaml's caCerts.additionalCACerts block

CA_DIR="${CA_DIR:-./ca}"
OUT="${OUT:-./ca-certs.snippet.yaml}"

if [ ! -d "$CA_DIR" ]; then
  echo "Directory not found: $CA_DIR" >&2
  echo "Drop the CAs downloaded from the OVHcloud control panel there." >&2
  exit 1
fi

shopt -s nullglob
certs=("$CA_DIR"/*.pem "$CA_DIR"/*.crt)
shopt -u nullglob

if [ ${#certs[@]} -eq 0 ]; then
  echo "No .pem or .crt files in $CA_DIR." >&2
  exit 1
fi

{
  echo "caCerts:"
  echo "  additionalCACerts:"
  for cert in "${certs[@]}"; do
    name="$(basename "$cert")"
    name="${name%.*}"

    if ! openssl x509 -in "$cert" -noout >/dev/null 2>&1; then
      echo "Unreadable certificate, skipped: $cert" >&2
      continue
    fi

    subject="$(openssl x509 -in "$cert" -noout -subject 2>/dev/null || true)"
    echo "    # $subject"
    echo "    - name: ovh-${name}"
    echo "      content: |"

    # re-encoded, not copied: a pasted PEM often carries trailing text keytool would choke on
    openssl x509 -in "$cert" -outform PEM 2>/dev/null | sed 's/^/        /'
  done
} > "$OUT"

echo "Fragment written to $OUT" >&2
echo "Paste it into deploy/opik/values.yaml, replacing the caCerts block." >&2
echo "Check the indentation: Helm silently ignores a misindented key." >&2
