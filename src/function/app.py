"""The triage step as a web service: one FastAPI app that runs on your laptop (uvicorn) and
on AWS Lambda (through Mangum, see handler.py) without changing a line.

    POST /triage   {"ticket": ..., "account": {...}, "policy_in": "user"}  ->  the triage record,
                   plus what only the function can know: cold start, import time, its own elapsed time
    GET  /         a health check: the same metadata, no model call
    GET  /docs     Swagger UI (locally; the deployed URL needs a signed request, see call.sh)

The model call, the retries and the fake provider are unchanged: src/system/triage.py and
src/system/plumbing.py are the same files as in the project repository.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Literal

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:  # the repository root, so "src.system" resolves here and inside the deployment package
    sys.path.insert(0, _ROOT)

_T0 = time.perf_counter()
from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from src.system.triage import DEFAULT_MODEL, triage  # noqa: E402
from google import genai  # noqa: E402, F401  (load the SDK now, so import time is part of the cold start)

INIT_MS = round((time.perf_counter() - _T0) * 1000)
INVOCATIONS = 0   # module state survives between warm invocations of the same sandbox

app = FastAPI(title="triage-url", version="1.0", description="The support-ticket triage step, behind a URL.")


class TriageRequest(BaseModel):
    ticket: str = Field(..., examples=["The water bottle from O-55010 leaks from the lid. I'd like a refund for it ($34)."])
    account: dict = Field(..., examples=[{"account_id": "A-11002", "status": "active", "tenure_months": 9,
                                          "recent_orders": [{"order_id": "O-55010", "total": 34.0, "items": ["water bottle"]}],
                                          "open_refunds": 0}])
    policy_in: Literal["user", "system"] = "user"


def check_token(x_lab_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("LAB_TOKEN")
    if expected and x_lab_token != expected:
        raise HTTPException(status_code=401, detail="bad or missing x-lab-token header")


def _meta(started: float, cold: bool) -> dict:
    return {"cold_start": cold, "init_ms": INIT_MS, "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "invocation": INVOCATIONS, "model": DEFAULT_MODEL, "provider": os.environ.get("PROVIDER", "gemini")}


@app.get("/")
def health() -> dict:
    global INVOCATIONS
    started = time.perf_counter(); cold = INVOCATIONS == 0; INVOCATIONS += 1
    return {"ok": True, "function": _meta(started, cold)}


@app.post("/triage")
def triage_endpoint(req: TriageRequest, _: None = Depends(check_token)) -> dict:
    global INVOCATIONS
    started = time.perf_counter(); cold = INVOCATIONS == 0; INVOCATIONS += 1
    provider = os.environ.get("PROVIDER", "gemini")   # PROVIDER=fake for a dry run with no key
    try:
        rec = triage(req.ticket, req.account, provider=provider, policy_in=req.policy_in)
    except SystemExit as e:  # plumbing.py gives up on a daily cap or a dead provider
        raise HTTPException(status_code=503, detail=str(e))
    rec["function"] = _meta(started, cold)
    print(json.dumps({"level": "info", "cold_start": cold, "action": rec["action"],
                      "latency_ms": rec["latency_ms"], "elapsed_ms": rec["function"]["elapsed_ms"]}))
    return rec
