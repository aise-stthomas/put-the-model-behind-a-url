"""The report: per slice, per scorer, as counts. Read against the requirement."""
from __future__ import annotations

from collections import defaultdict

from .golden import tags
from .scorers import SCORERS

Table = dict[tuple[str, str], list[bool]]  # (slice tag, scorer name) -> results


def per_slice(items: dict[str, dict], records: list[dict]) -> Table:
    """Apply every scorer to every recorded output and file the result under every slice tag."""
    table: Table = defaultdict(list)
    for rec in records:
        item = items[rec["id"]]
        for name, (score, _) in SCORERS.items():
            result = score(item, rec)
            if result is None:
                continue
            for tag in tags(item):
                table[tag, name].append(result)
    return table


CONDITION_LABEL = {"user": "policy sent in the user text, beside the ticket",
                   "system": "policy sent as the system instruction"}


def _rate(cell: list[bool] | None) -> float | None:
    return None if not cell else sum(cell) / len(cell)


def _floor(cells: list[list[bool] | None]) -> float | None:
    rates = [r for r in map(_rate, cells) if r is not None]
    return None if not rates else round(100 * (max(rates) - min(rates)))


def _fmt(cell: list[bool] | None) -> str:
    return "-" if cell is None else f"{sum(cell)}/{len(cell)}"


def summary(condition: str, runs: list[tuple[str, list[dict]]], tables: list[Table], items: dict[str, dict],
            detail: bool = False) -> None:
    """What happened in one condition, in plain words, then the numbers."""
    records = [r for _, rs in runs for r in rs]
    n_items = len({r["id"] for r in records})
    policy_in = next((r.get("policy_in") for r in records), "user")
    model = next((r.get("model") for r in records), "?")
    print(f"\n{'=' * 78}\n{condition.upper()}: {CONDITION_LABEL.get(policy_in, policy_in)}")
    print(f"{len(runs)} runs over the same {n_items} tickets · {model}\n")

    # the headline: the right action
    all_cells = [t.get(("all", "action")) for t in tables]
    print("RIGHT ACTION  (did the model choose the route the policy requires?)")
    print("  " + "   ".join(f"{name}: {_fmt(c)} tickets" for (name, _), c in zip(runs, all_cells)))
    fl = _floor(all_cells)
    print(f"  noise floor: {fl} points  (best run minus worst run, with nothing changed)")
    wrong: dict[str, int] = {}
    for _, rs in runs:
        for r in rs:
            if r["action"] != items[r["id"]]["expected_action"]:
                wrong[r["id"]] = wrong.get(r["id"], 0) + 1
    every = sorted(i for i, k in wrong.items() if k == len(runs))
    some = sorted(i for i, k in wrong.items() if k < len(runs))
    print(f"  wrong in every run: {', '.join(every) or 'none'}")
    print(f"  wrong in some runs: {', '.join(f'{i} ({wrong[i]} of {len(runs)})' for i in some) or 'none'}")

    # by slice, for the action
    slices = sorted({tag for t in tables for tag, _ in t})
    size = {tag: sum(1 for i in items.values() if tag in tags(i)) for tag in slices}
    print(f"\n  {'by slice':30s}{'tickets':>8s}" + "".join(f"{n:>8s}" for n, _ in runs) + f"{'floor':>8s}")
    for tag in slices:
        cells = [t.get((tag, "action")) for t in tables]
        if all(c is None for c in cells):
            continue
        fl = _floor(cells)
        print(f"  {tag:30s}{size[tag]:>8d}" + "".join(f"{_fmt(c):>8s}" for c in cells) + f"{'' if fl is None else str(fl) + ' pts':>8s}")
    print("  (a slice is a tag on tickets in golden/golden.json; a cell is right / tickets in the slice)")

    # the other checks, one line each
    print("\nOTHER CHECKS  (all tickets, per run)")
    for name, (_, what) in SCORERS.items():
        if name == "action":
            continue
        cells = [t.get(("all", name)) for t in tables]
        if all(c is None for c in cells):
            note = "does not apply to these records"
            print(f"  {name:20s} {what:44s} {note}")
            continue
        print(f"  {name:20s} {what:44s} " + "  ".join(f"{_fmt(c):>6s}" for c in cells))
    if detail:
        for name, (_, what) in SCORERS.items():
            if name == "action":
                continue
            print(f"\n  {name}: {what}")
            for tag in slices:
                cells = [t.get((tag, name)) for t in tables]
                if all(c is None for c in cells):
                    continue
                print(f"  {tag:30s}{size[tag]:>8d}" + "".join(f"{_fmt(c):>8s}" for c in cells))


def compare(a: str, tables_a: list[Table], b: str, tables_b: list[Table], items: dict[str, dict]) -> None:
    """Two conditions side by side, right action per slice, and a verdict for each slice.

    Verdict: the gap between the two means is compared with the larger of the two noise
    floors. Larger gap: helped or hurt. Smaller or equal: cannot tell.
    """
    slices = sorted({tag for t in tables_a + tables_b for tag, _ in t})
    size = {tag: sum(1 for i in items.values() if tag in tags(i)) for tag in slices}
    print(f"\n{'=' * 78}\n{b.upper()} vs {a.upper()}: did the change help?  (right action, per slice)\n")
    print(f"  {'slice':30s}{'tickets':>8s}  {a + ' runs':>18s}  {b + ' runs':>18s}  {'floor':>6s}  verdict")
    for tag in slices:
        ca = [t.get((tag, "action")) for t in tables_a]
        cb = [t.get((tag, "action")) for t in tables_b]
        if all(c is None for c in ca) or all(c is None for c in cb):
            continue
        ra = [r for r in map(_rate, ca) if r is not None]
        rb = [r for r in map(_rate, cb) if r is not None]
        floor = max(_floor(ca) or 0, _floor(cb) or 0)
        gap = round(100 * (sum(rb) / len(rb) - sum(ra) / len(ra)))
        if gap == 0 and floor == 0:
            verdict = "no change"
        elif abs(gap) > floor:
            verdict = f"helped (+{gap} pts, floor {floor})" if gap > 0 else f"hurt ({gap} pts, floor {floor})"
        else:
            verdict = f"cannot tell (gap {gap:+d}, floor {floor})"
        fa = ",".join(str(sum(c)) for c in ca if c is not None) + f" of {len(ca[0])}"
        fb = ",".join(str(sum(c)) for c in cb if c is not None) + f" of {len(cb[0])}"
        print(f"  {tag:30s}{size[tag]:>8d}  {fa:>18s}  {fb:>18s}  {floor:>4d}    {verdict}")
    print("\n  helped / hurt: the gap between the two averages is larger than the noise floor.")
    print("  cannot tell:   the gap is inside the noise floor; the runs already move that much by themselves.")
    print("  A slice of one or two tickets moves 50 to 100 points on its own; it cannot tell you anything yet.")
