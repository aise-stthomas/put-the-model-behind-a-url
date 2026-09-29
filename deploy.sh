#!/usr/bin/env bash
# Deploy the triage step as a function behind a URL, in the AWS Academy Learner Lab.
#
#   ./deploy.sh                    build the package, create or update the function, print the URL
#   ./deploy.sh --timeout 3        the same, with a 3-second time limit (Part 4)
#   ./deploy.sh --memory 1024      more memory, which on Lambda is also more CPU
#   ./deploy.sh --recycle          no rebuild: force every sandbox cold, so the next call is a cold start
#
# What it assumes: the AWS CLI with a live Learner Lab session pasted into ~/.aws/credentials
# (Configuring AWS, section 3), uv, and your Gemini key in .env. It uses the pre-created
# LabRole, never creates IAM anything, and stays in us-east-1.
set -euo pipefail
cd "$(dirname "$0")"

FN="${FUNCTION_NAME:-triage-url}"
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
TIMEOUT=30; MEMORY=512; RECYCLE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --memory)  MEMORY="$2"; shift 2 ;;
    --recycle) RECYCLE=1; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
done

# --- what we need ---------------------------------------------------------------------
command -v aws >/dev/null || { echo "aws CLI not found: brew install awscli (or see Configuring AWS)"; exit 1; }
command -v uv  >/dev/null || { echo "uv not found: see the README"; exit 1; }
[ -f .env ] || { echo "no .env: cp .env.example .env and paste your Gemini key"; exit 1; }
set -a; . ./.env; set +a
: "${GEMINI_API_KEY:?GEMINI_API_KEY is not set in .env}"
if [ -z "${LAB_TOKEN:-}" ]; then
  LAB_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  printf '\nLAB_TOKEN=%s\n' "$LAB_TOKEN" >> .env
  echo "made a LAB_TOKEN and saved it in .env (the function checks it on every request)"
fi

ACCOUNT="$(aws sts get-caller-identity --query Account --output text 2>/dev/null)" \
  || { echo "aws sts get-caller-identity failed: start a Learner Lab session and paste fresh credentials"; exit 1; }
ROLE="arn:aws:iam::${ACCOUNT}:role/LabRole"
ENV_VARS="Variables={GEMINI_API_KEY=${GEMINI_API_KEY},LAB_TOKEN=${LAB_TOKEN},DEPLOYED_AT=$(date +%s)}"

# --- recycle: a config change alone replaces every warm sandbox ------------------------
if [ "$RECYCLE" = 1 ]; then
  aws lambda update-function-configuration --function-name "$FN" --environment "$ENV_VARS" >/dev/null
  aws lambda wait function-updated --function-name "$FN"
  echo "recycled: the next call to $FN is a cold start"
  exit 0
fi

# --- build: the dependencies for Lambda's Linux, plus the system and the handler -------
echo "building the package..."
rm -rf build && mkdir -p build/pkg
uv pip install --quiet --target build/pkg \
  --python-platform x86_64-manylinux_2_28 --python-version 3.12 \
  "google-genai>=2.23" "python-dotenv>=1.0" "fastapi>=0.115" "mangum>=0.17"
cp -R src build/pkg/src
find build/pkg/src -name "__pycache__" -type d -prune -exec rm -rf {} +
( cd build/pkg && zip -qr ../function.zip . -x '*.pyc' -x '*/__pycache__/*' )
echo "  $(du -h build/function.zip | cut -f1) zipped, $(du -sh build/pkg | cut -f1) unpacked"

# --- create or update ------------------------------------------------------------------
if aws lambda get-function --function-name "$FN" >/dev/null 2>&1; then
  echo "updating $FN..."
  aws lambda update-function-code --function-name "$FN" --zip-file "fileb://build/function.zip" >/dev/null
  aws lambda wait function-updated --function-name "$FN"
  aws lambda update-function-configuration --function-name "$FN" \
    --timeout "$TIMEOUT" --memory-size "$MEMORY" --environment "$ENV_VARS" >/dev/null
  aws lambda wait function-updated --function-name "$FN"
else
  echo "creating $FN as $ROLE..."
  aws lambda create-function --function-name "$FN" \
    --runtime python3.12 --architectures x86_64 --handler src.function.handler.handler \
    --role "$ROLE" --zip-file "fileb://build/function.zip" \
    --timeout "$TIMEOUT" --memory-size "$MEMORY" --environment "$ENV_VARS" >/dev/null
  aws lambda wait function-active --function-name "$FN"
fi

# --- the URL: IAM-authenticated. The Learner Lab blocks anonymous function URLs (a public
# --- URL answers 403 whatever the resource policy says), so callers sign requests with the
# --- same session credentials this script used. record.py does that for you.
URL="$(aws lambda get-function-url-config --function-name "$FN" --query FunctionUrl --output text 2>/dev/null || true)"
if [ -z "$URL" ] || [ "$URL" = "None" ]; then
  URL="$(aws lambda create-function-url-config --function-name "$FN" --auth-type AWS_IAM --query FunctionUrl --output text)"
else
  aws lambda update-function-url-config --function-name "$FN" --auth-type AWS_IAM >/dev/null
fi

# remember the URL for record.py
if grep -q '^LAB_URL=' .env; then
  sed -i.bak "s|^LAB_URL=.*|LAB_URL=${URL}triage|" .env && rm -f .env.bak
else
  printf 'LAB_URL=%s\n' "${URL}triage" >> .env
fi

echo
echo "deployed: $FN   timeout ${TIMEOUT}s   memory ${MEMORY} MB"
echo "url:      ${URL}triage   (saved to .env as LAB_URL)"
echo
echo "try it:   ./call.sh src/function/sample-event-body.json      (curl, signed with your session credentials)"
echo "record:   uv run record.py --provider http --runs 3"
echo "logs:     aws logs tail /aws/lambda/$FN --follow"
