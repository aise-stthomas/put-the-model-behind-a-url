"""Record: run the triage step over the golden set and keep every call.

    uv run record.py --runs 1                       # local: the model called from this process -> data/fixtures/local/
    uv run record.py --provider http --runs 3       # over HTTP: the deployed function -> data/fixtures/http/
    uv run record.py --provider http --url http://127.0.0.1:9000 --runs 1    # the local server
    uv run record.py --provider fake --runs 1       # no key, NOT a model -> data/fixtures/fake/
    uv run record.py --provider http --name http-3s --runs 2                 # any condition, named yourself

The URL and the token come from .env (LAB_URL, LAB_TOKEN; deploy.sh writes them) or from
--url / --token. Writes data/fixtures/<condition>/run-<k>.jsonl, one line per call, as each
call lands. Resumable: a call already in the file is never made again.

Over HTTP every record carries two clocks: the model's own latency, measured inside the
function, and client_ms, the whole round trip measured here. A call that died at the
function's time limit is recorded too, as action "error". Calls to a deployed function
URL are signed with your AWS session credentials (the Learner Lab does not allow
anonymous function URLs); a local server needs no signature.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from src.harness import fixtures, golden
from src.system import DEFAULT_MODEL, triage

load_dotenv()


def _signer():
    """SigV4 for a function URL with IAM auth: the same credentials deploy.sh used, from
    ~/.aws/credentials. Returns None when there are none (a local server needs no signature)."""
    try:
        import botocore.session
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
    except ImportError:
        return None
    creds = botocore.session.get_session().get_credentials()
    if creds is None:
        return None
    auth = SigV4Auth(creds, "lambda", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

    def sign(url: str, body: bytes, headers: dict) -> dict:
        req = AWSRequest(method="POST", url=url, data=body, headers=headers)
        auth.add_auth(req)
        return dict(req.headers)
    return sign


_SIGN = None


def call_http(url: str, token: str | None, ticket: str, account: dict, policy_in: str, timeout: float) -> dict:
    global _SIGN
    body = json.dumps({"ticket": ticket, "account": account, "policy_in": policy_in}).encode()
    headers = {"content-type": "application/json"}
    if token:
        headers["x-lab-token"] = token
    if "lambda-url" in url:           # a deployed function: sign it (Learner Lab URLs require IAM auth)
        if _SIGN is None:
            _SIGN = _signer() or (lambda u, b, h: h)
        headers = _SIGN(url, body, headers)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rec = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")[:200]
        rec = {"action": "error", "refund_amount": None, "rationale": None, "error": f"HTTP {e.code}: {text}"}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        rec = {"action": "error", "refund_amount": None, "rationale": None, "error": f"{type(e).__name__}: {e}"}
    rec["client_ms"] = round((time.perf_counter() - t0) * 1000)
    return rec


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", choices=["gemini", "fake", "http"], default="gemini")
    p.add_argument("--url", default=os.environ.get("LAB_URL"), help="the function URL (default: LAB_URL from .env)")
    p.add_argument("--token", default=os.environ.get("LAB_TOKEN"), help="the shared secret (default: LAB_TOKEN from .env)")
    p.add_argument("--name", help="the condition; default: local, http, or fake")
    p.add_argument("--runs", type=int, default=1, help="passes over the whole suite")
    p.add_argument("--policy-in", choices=["user", "system"], default="user")
    p.add_argument("--limit", type=int, help="only the first N tickets")
    p.add_argument("--timeout", type=float, default=90, help="seconds to wait for one HTTP call")
    args = p.parse_args()
    name = args.name or {"gemini": "local", "http": "http", "fake": "fake"}[args.provider]
    if args.provider == "http" and not args.url:
        raise SystemExit("no URL: run ./deploy.sh, or pass --url")

    items = golden.load_golden()[: args.limit]
    accounts = golden.load_accounts()
    where = args.url if args.provider == "http" else f"{DEFAULT_MODEL} via {args.provider}, in this process"
    for run in range(1, args.runs + 1):
        path = fixtures.run_path(name, run)
        done = fixtures.recorded_ids(path)
        todo = [i for i in items if i["id"] not in done]
        print(f"{name} run {run}: {len(done)} recorded, {len(todo)} to go  ({where})", flush=True)
        for item in todo:
            if args.provider == "http":
                rec = call_http(args.url, args.token, item["ticket"], accounts[item["account"]], args.policy_in, args.timeout)
            else:
                rec = triage(item["ticket"], accounts[item["account"]], provider=args.provider, policy_in=args.policy_in)
            rec.update({"id": item["id"], "run": run, "condition": name})
            fixtures.append(path, rec)
            fn = rec.get("function") or {}
            tag = "cold" if fn.get("cold_start") else ("warm" if fn else "")
            ms = f"{rec.get('client_ms', rec.get('latency_ms', '?'))} ms"
            what = rec["action"] if rec["action"] != "error" else f"error: {rec.get('error', '')[:60]}"
            print(f"  {item['id']}  {what:9s} {'' if rec.get('refund_amount') is None else rec['refund_amount']}  {ms:>9s} {tag}", flush=True)


if __name__ == "__main__":
    main()
