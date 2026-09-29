"""Latency: what the round trip cost, from the fixtures, per run.

    uv run latency.py http           # every run under data/fixtures/http/
    uv run latency.py http http-3s   # several conditions

Three numbers per run: cold starts (how many, and how long they took), warm calls (median
and 95th percentile of the round trip), and errors (how many, and why). The function's own
clocks are shown beside the client's so you can see where the time went: import (init),
the model call (latency_ms), and everything else (network, the function runtime).
"""
from __future__ import annotations

import sys

from src.harness import fixtures


def pct(xs: list[int], q: float) -> int | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))
    return xs[k]


def main() -> None:
    conditions = sys.argv[1:] or ["http"]
    for cond in conditions:
        runs = fixtures.runs(cond)
        if not runs:
            print(f"no fixtures under data/fixtures/{cond}")
            continue
        print(f"\n{'=' * 78}\n{cond.upper()}")
        for name, recs in runs:
            http = [r for r in recs if "client_ms" in r]
            if not http:
                print(f"  {name}: recorded in-process, no round trip to measure (model latency p50 "
                      f"{pct([r['latency_ms'] for r in recs], .5)} ms)")
                continue
            ok = [r for r in http if r["action"] != "error"]
            errors = [r for r in http if r["action"] == "error"]
            cold = [r for r in ok if r.get("function", {}).get("cold_start")]
            warm = [r for r in ok if r.get("function") and not r["function"].get("cold_start")]
            print(f"\n  {name}: {len(http)} calls · {len(ok)} completed · {len(errors)} errors")
            if cold:
                for r in cold:
                    f = r["function"]; rest = r["client_ms"] - f["init_ms"] - r["latency_ms"]
                    if rest >= 0:
                        print(f"    cold start   round trip {r['client_ms']:>6} ms   = init {f['init_ms']} ms + model {r['latency_ms']} ms + the rest {rest} ms (network, the runtime)")
                    else:
                        print(f"    cold start   round trip {r['client_ms']:>6} ms   (init {f['init_ms']} ms happened before the request: a local server, not a cold sandbox)")
            else:
                print("    cold start   none in this run (the sandbox was already warm)")
            if warm:
                rt = [r["client_ms"] for r in warm]; ml = [r["latency_ms"] for r in warm]
                print(f"    warm         round trip p50 {pct(rt, .5):>6} ms · p95 {pct(rt, .95):>6} ms · max {max(rt):>6} ms")
                print(f"                 of which model p50 {pct(ml, .5):>6} ms · p95 {pct(ml, .95):>6} ms   (the URL costs the difference)")
            if errors:
                reasons: dict[str, int] = {}
                for r in errors:
                    key = r.get("error", "?")[:70]
                    reasons[key] = reasons.get(key, 0) + 1
                for k, n in reasons.items():
                    print(f"    error ×{n}     {k}")
                rt = [r["client_ms"] for r in errors]
                print(f"                 errors came back after p50 {pct(rt, .5)} ms · max {max(rt)} ms")


if __name__ == "__main__":
    main()
