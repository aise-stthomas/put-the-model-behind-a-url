"""Scorers: each turns (item, output) into True, False, or None (does not apply).

The same shape as the project's harness, with one scorer added for tonight: did the
call complete at all? A call that died at the function's time limit is a sample too.
"""
from __future__ import annotations


def score_completed(item: dict, output: dict) -> bool:
    """The call returned a decision. False when the function timed out or the URL errored."""
    return output["action"] != "error"


def score_action(item: dict, output: dict) -> bool:
    """Exact match on the route. Malformed output and a dead call are failures, never dropped."""
    return output["action"] == item["expected_action"]


def score_amount(item: dict, output: dict) -> bool | None:
    """When money moves, the amount is within what the policy allows for this ticket."""
    if output["action"] not in ("refund", "hold"):
        return None
    if output["refund_amount"] is None or item["max_refund"] is None:
        return False
    return output["refund_amount"] <= item["max_refund"]


def score_format(item: dict, output: dict) -> bool | None:
    """The output parsed as a decision at all. Does not apply to a call that never returned."""
    if output["action"] == "error":
        return None
    return output["action"] != "malformed"


SCORERS = {  # name: (function, what it checks)
    "completed": (score_completed, "the call returned a decision at all"),
    "action":    (score_action,    "the route is the one the policy requires"),
    "amount":    (score_amount,    "the amount never exceeds what the policy allows"),
    "format":    (score_format,    "the output parsed as a decision"),
}
