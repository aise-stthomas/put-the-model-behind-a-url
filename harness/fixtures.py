"""Fixtures: every model output, saved as it lands, under fixtures/<condition>/run-<k>.jsonl.

Record once, score many times. Nothing in here calls the model.
"""
from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path("fixtures")


def run_path(condition: str, run: int) -> Path:
    return FIXTURES / condition / f"run-{run}.jsonl"


def judge_path(condition: str, run_name: str) -> Path:
    """The judge's verdicts for one run: fixtures/<condition>/judge-<run>.jsonl."""
    return FIXTURES / condition / f"judge-{run_name}.jsonl"


def recorded_ids(path: Path) -> set[str]:
    """Which tickets this run file already holds, so a rerun continues rather than repeats."""
    if not path.exists():
        return set()
    return {json.loads(line)["id"] for line in path.read_text().splitlines() if line.strip()}


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def runs(condition: str) -> list[tuple[str, list[dict]]]:
    """(run name, records) for every run recorded under a condition, in order.

    If the judge has been run on it, each record also carries its verdicts under "judge".
    """
    out = []
    for path in sorted((FIXTURES / condition).glob("run-*.jsonl")):
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        jpath = judge_path(condition, path.stem)
        if jpath.exists():
            verdicts = {j["id"]: j for j in (json.loads(l) for l in jpath.read_text().splitlines() if l.strip())}
            for r in records:
                if r["id"] in verdicts:
                    r["judge"] = {k: v for k, v in verdicts[r["id"]].items() if k not in ("id", "run", "condition")}
        out.append((path.stem, records))
    return out
