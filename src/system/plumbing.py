"""Plumbing: retrying when the provider says "slow down", and a fake provider for
checking your harness with no key. Not part of the system under test.
"""
from __future__ import annotations

import json
import random
import time


def _quota(e) -> tuple[bool, float | None]:
    """Read a 429's details: (is it a daily cap?, seconds the provider asked us to wait).

    Gemini says "check your plan and billing details" on *every* 429, so the words tell
    you nothing. The structured details do: a QuotaFailure names the quota that ran out
    (...PerMinute... or ...PerDay...), and a RetryInfo says how long until it refills.
    """
    body = e.details if isinstance(e.details, dict) else {}
    body = body.get("error", body) if isinstance(body.get("error"), dict) else body
    daily, wait = False, None
    for d in body.get("details") or []:
        if not isinstance(d, dict):
            continue
        for v in d.get("violations") or []:
            if "perday" in (str(v.get("quotaId", "")) + str(v.get("quotaMetric", ""))).lower():
                daily = True
        delay = d.get("retryDelay")
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                wait = float(delay[:-1])
            except ValueError:
                pass
    msg = (getattr(e, "message", None) or "").lower()
    if "per day" in msg or "daily" in msg:
        daily = True
    return daily, wait


def with_retries(sample):
    """Wrap a sample(prompt, temperature, model) function so a run finishes.

    The free tier *is* a per-minute rate limit: a 429 means "the minute is not over
    yet", so wait as long as the provider asks (or a bit, growing, if it does not say)
    and try again. The daily cap, or a provider that keeps returning 5xx, will not get
    better by waiting, so stop and say why.
    """
    def call(prompt: str, temperature: float | None, model: str, system: str | None = None) -> str:
        from google.genai import errors

        switch = ("Everything recorded so far is kept: rerun the same command later (or "
                  "with your partner's key) and it continues where it stopped.")
        backoff, waited, server_errors = 10.0, 0.0, 0
        while True:
            try:
                return sample(prompt, temperature, model, system)
            except errors.ClientError as e:
                if e.code != 429:
                    raise
                daily, asked = _quota(e)
                if daily:
                    raise SystemExit(f"\n{model} refused: the daily quota on this key is used up.\n{switch}")
                if waited > 15 * 60:
                    raise SystemExit(f"\n{model} has been rate limiting for 15 minutes; something other "
                                     f"than the per-minute limit is wrong. {switch}")
                delay = (asked + 1) if asked else backoff
                backoff = min(backoff * 2, 60)
                print(f"    rate limited; sleeping {delay:.0f}s", flush=True)
                time.sleep(delay)
                waited += delay
            except errors.ServerError as e:
                server_errors += 1
                if server_errors == 1:
                    print(f"    server error {e.code}: {getattr(e, 'message', str(e))[:120]}", flush=True)
                if server_errors >= 5:
                    raise SystemExit(f"\n{model} keeps returning {e.code}; that is the provider, not you. {switch}")
                print(f"    retrying in {backoff:.0f}s", flush=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
    return call


def fake_model(prompt: str, temperature: float | None, model: str, system: str | None = None) -> str:
    """NOT a model. Returns a random decision so you can check your harness (recording,
    scoring, tables) with no key and no quota. Any conclusion you draw from fake output
    is a conclusion about this function, not about a model.
    """
    import re
    dollars = [float(x) for x in re.findall(r"\$(\d+(?:\.\d+)?)", prompt.split("TICKET:")[-1])]
    action = random.choices(["answer", "refund", "hold", "escalate"], weights=[4, 3, 2, 1])[0]
    amount = random.choice(dollars) if dollars and action in ("refund", "hold") else None
    if random.random() < 0.03:
        return "Sure! Here is my decision: refund it."  # malformed on purpose
    return json.dumps({"action": action, "refund_amount": amount, "rationale": "fake"})
