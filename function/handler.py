"""The triage step, behind a URL.

This file is the whole function. It runs on AWS Lambda (handler(event, context)), and it
runs on your laptop the same way (python function/handler.py, or function/local_server.py).
Everything it does:

    check the shared token  ->  read the ticket and the account from the request body
    ->  call the frozen triage() exactly as record.py does locally  ->  return the record,
    plus what only the function can know: was this a cold start, how long did the
    function itself take, how long did importing everything take.

The model call, the retries and the fake provider are unchanged: system/triage.py and
system/plumbing.py are the same files as in the project repository.
"""
from __future__ import annotations

import base64
import json
import os
import time

import sys
if not os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "system")):
    # on your laptop this file lives in function/; on Lambda it sits beside system/
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_T0 = time.perf_counter()
from system.triage import triage  # noqa: E402  (import time is part of the cold start)
from google import genai  # noqa: E402, F401  (force the SDK to load now, not on the first call)

INIT_MS = round((time.perf_counter() - _T0) * 1000)
INVOCATIONS = 0   # module state survives between warm invocations of the same sandbox


def _response(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def handler(event: dict, context=None) -> dict:
    global INVOCATIONS
    started = time.perf_counter()
    cold = INVOCATIONS == 0
    INVOCATIONS += 1

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    expected = os.environ.get("LAB_TOKEN")
    if expected and headers.get("x-lab-token") != expected:
        return _response(401, {"error": "bad or missing x-lab-token header"})

    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        req = json.loads(raw)
        ticket, account = req["ticket"], req["account"]
    except (ValueError, KeyError, TypeError) as e:
        return _response(400, {"error": f"body must be JSON with 'ticket' and 'account': {e}"})

    provider = os.environ.get("PROVIDER", "gemini")   # PROVIDER=fake for a dry run with no key
    try:
        rec = triage(ticket, account, provider=provider, policy_in=req.get("policy_in", "user"))
    except SystemExit as e:  # plumbing.py gives up on a daily cap or a dead provider
        return _response(503, {"error": str(e)})

    rec["function"] = {
        "cold_start": cold,
        "init_ms": INIT_MS,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "invocation": INVOCATIONS,
        "request_id": getattr(context, "aws_request_id", None),
    }
    print(json.dumps({"level": "info", "cold_start": cold, "action": rec["action"],
                      "latency_ms": rec["latency_ms"], "elapsed_ms": rec["function"]["elapsed_ms"]}))
    return _response(200, rec)


if __name__ == "__main__":
    # Rung 1: run the handler as a plain function, on your laptop, with the fake provider.
    os.environ.setdefault("PROVIDER", "fake")
    event = json.load(open(os.path.join(os.path.dirname(__file__), "sample-event.json")))
    out = handler(event, None)
    print(out["statusCode"])
    print(json.dumps(json.loads(out["body"]), indent=2))
