#!/usr/bin/env bash
# One signed request to the deployed function, with curl. Usage: ./call.sh src/function/sample-event-body.json
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
: "${LAB_URL:?run ./deploy.sh first}"
AK="$(aws configure get aws_access_key_id)"; SK="$(aws configure get aws_secret_access_key)"; ST="$(aws configure get aws_session_token || true)"
curl -s -X POST "$LAB_URL" --aws-sigv4 "aws:amz:us-east-1:lambda" --user "$AK:$SK" \
  ${ST:+-H "x-amz-security-token: $ST"} -H "x-lab-token: ${LAB_TOKEN:-}" \
  -H 'content-type: application/json' -d @"${1:-src/function/sample-event-body.json}"
echo
