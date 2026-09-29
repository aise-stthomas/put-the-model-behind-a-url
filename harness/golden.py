"""The golden set: tickets with the right answer attached, tagged by slice."""
from __future__ import annotations

import json
from pathlib import Path

GOLDEN = Path("golden/golden.json")
ACCOUNTS = Path("golden/accounts.json")


def load_golden() -> list[dict]:
    items = json.loads(GOLDEN.read_text())
    assert isinstance(items, list), "golden.json is a JSON array of tickets"
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)), "duplicate id in golden.json"
    return items


def load_accounts() -> dict[str, dict]:
    return json.loads(ACCOUNTS.read_text())


def tags(item: dict) -> list[str]:
    """Every slice an item belongs to. 'all' is every item; 'ambiguous' is a slice too."""
    return ["all"] + item["slices"] + (["ambiguous"] if item.get("ambiguous") else [])
