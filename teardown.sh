#!/usr/bin/env bash
# Remove the function and its URL. Nothing else was created.
set -euo pipefail
FN="${FUNCTION_NAME:-triage-url}"
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
aws lambda delete-function-url-config --function-name "$FN" 2>/dev/null || true
aws lambda delete-function --function-name "$FN" 2>/dev/null && echo "deleted $FN" || echo "$FN was not there"
