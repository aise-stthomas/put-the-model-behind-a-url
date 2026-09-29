"""The Lambda entry point: the FastAPI app in app.py, adapted to Lambda's event shape by Mangum.

Run this file directly to exercise exactly that path on your laptop, with no AWS: it builds
the event a function URL would deliver and calls the handler.

    uv run src/function/handler.py              # fake provider unless PROVIDER=gemini
"""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mangum import Mangum  # noqa: E402
from src.function.app import app  # noqa: E402

handler = Mangum(app, lifespan="off")


if __name__ == "__main__":
    os.environ.setdefault("PROVIDER", "fake")
    body = open(os.path.join(os.path.dirname(__file__), "sample-event-body.json")).read()
    headers = {"content-type": "application/json"}
    if os.environ.get("LAB_TOKEN"):  # once deploy.sh has made a token, present it, as call.sh and record.py do
        headers["x-lab-token"] = os.environ["LAB_TOKEN"]
    event = {  # what a Lambda function URL delivers (the API Gateway v2 shape)
        "version": "2.0", "routeKey": "$default", "rawPath": "/triage", "rawQueryString": "",
        "headers": headers, "requestContext": {"http": {"method": "POST", "path": "/triage", "sourceIp": "127.0.0.1"}},
        "body": body, "isBase64Encoded": False,
    }
    out = handler(event, None)
    print(out["statusCode"])
    print(json.dumps(json.loads(out["body"]), indent=2))
