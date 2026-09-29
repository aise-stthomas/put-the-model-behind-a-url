#!/usr/bin/env bash
# Remove everything the lab created, in AWS and here.
#
#   ./teardown.sh            the function and its URL; the build directory; the LAB_URL and
#                            LAB_TOKEN lines in .env (your Gemini key stays). The CloudWatch
#                            log group is kept: it costs nothing, and it is your record of
#                            every call the function handled.
#   ./teardown.sh --keep-env leave .env untouched
#
# Nothing else was created: no roles, no buckets, no tables. Fixtures are your data and are
# never touched.
set -uo pipefail
cd "$(dirname "$0")"
FN="${FUNCTION_NAME:-triage-url}"
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
KEEP_ENV=0; [ "${1:-}" = "--keep-env" ] && KEEP_ENV=1

if command -v aws >/dev/null && aws sts get-caller-identity >/dev/null 2>&1; then
  if aws lambda delete-function-url-config --function-name "$FN" >/dev/null 2>&1; then echo "removed the URL of $FN"; fi
  if aws lambda delete-function --function-name "$FN" >/dev/null 2>&1; then echo "deleted the function $FN"; else echo "the function $FN was not there"; fi
  echo "kept the log group /aws/lambda/$FN (free; aws logs tail /aws/lambda/$FN --since 1d to read it)"
  echo "left in AWS from this lab: the log group only"
else
  echo "no AWS session (aws sts get-caller-identity failed): skipping the AWS side."
  echo "start a Learner Lab session, paste credentials, and run this again to delete the function."
fi

rm -rf build && echo "removed build/"
if [ "$KEEP_ENV" = 0 ] && [ -f .env ]; then
  sed -i.bak '/^LAB_URL=/d; /^LAB_TOKEN=/d' .env && rm -f .env.bak
  echo "removed LAB_URL and LAB_TOKEN from .env (your Gemini key is still there)"
fi
