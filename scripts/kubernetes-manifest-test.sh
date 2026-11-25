#!/usr/bin/env bash
# Lint the Helm chart, render the supported configurations, and validate every
# Kubernetes object against the upstream schemas. This does not contact a
# cluster; the test-cluster procedure is documented in the chart README.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

chart="deploy/kubernetes/chore-tracker"
release="chore-tracker"
namespace="chore-tracker"

if [[ -n "${KUBECONFORM:-}" ]]; then
  kubeconform="${KUBECONFORM}"
elif command -v kubeconform >/dev/null 2>&1; then
  kubeconform="$(command -v kubeconform)"
else
  echo "kubeconform is required. Install it from https://github.com/yannh/kubeconform" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

echo "Linting the chart with default and smoke-test values"
helm lint --strict "${chart}"
helm lint --strict "${chart}" --values "${chart}/values.smoke.yaml"

render() {
  local output="$1"
  shift
  helm template "${release}" "${chart}" --namespace "${namespace}" "$@" > "${output}"
}

echo "Rendering chart variants"
render "${tmp}/default.yaml"
render "${tmp}/smoke.yaml" --values "${chart}/values.smoke.yaml"
render "${tmp}/secret.yaml" \
  --set secrets.existingSecret=chore-tracker-smtp \
  --set config.emailTransport=smtp \
  --set config.emailFromAddress=chores@example.test \
  --set config.smtpHost=mail.example.test \
  --set config.smtpUsername=mailer
render "${tmp}/no-ingress.yaml" \
  --set ingress.enabled=false \
  --set config.appOrigin=http://chore-tracker.test \
  --set config.passkeyOrigin=http://chore-tracker.test \
  --set config.passkeyRpId=chore-tracker.test
render "${tmp}/existing-pvc.yaml" --set persistence.existingClaim=existing-sqlite
render "${tmp}/no-tls.yaml" --set ingress.tls.enabled=false

echo "Checking deployment invariants"
helm template "${release}" "${chart}" --namespace "${namespace}" \
  --show-only templates/deployment-backend.yaml | grep -q 'replicas: 1'
helm template "${release}" "${chart}" --namespace "${namespace}" \
  --show-only templates/deployment-backend.yaml | grep -q 'type: Recreate'
helm template "${release}" "${chart}" --namespace "${namespace}" \
  --show-only templates/deployment-backend.yaml | grep -q 'path: /health/live'
helm template "${release}" "${chart}" --namespace "${namespace}" \
  --show-only templates/deployment-backend.yaml | grep -q 'path: /health/ready'
helm template "${release}" "${chart}" --namespace "${namespace}" \
  --show-only templates/deployment-backend.yaml | grep -q 'persistentVolumeClaim'

grep -q 'CHORE_TRACKER_APP_ORIGIN: "https://chore-tracker.example.test"' "${tmp}/default.yaml"
grep -q 'CHORE_TRACKER_APP_ORIGIN: "http://chore-tracker.test"' "${tmp}/no-ingress.yaml"
grep -q 'CHORE_TRACKER_APP_ORIGIN: "http://chore-tracker.example.test"' "${tmp}/no-tls.yaml"
! grep -q 'CHORE_TRACKER_SMTP_' "${tmp}/default.yaml"
! grep -q 'CHORE_TRACKER_EMAIL_TRANSPORT' "${tmp}/smoke.yaml"
grep -q 'CHORE_TRACKER_SMTP_PASSWORD_FILE: "/run/secrets/smtp_password"' "${tmp}/secret.yaml"
grep -q 'claimName: existing-sqlite' "${tmp}/existing-pvc.yaml"
! grep -q '^kind: Secret' "${tmp}"/*.yaml
! grep -q '^kind: PersistentVolumeClaim' "${tmp}/existing-pvc.yaml"

echo "Validating Kubernetes schemas"
"${kubeconform}" -strict -summary -kubernetes-version 1.31.0 "${tmp}"/*.yaml

echo "Kubernetes manifest validation passed"
