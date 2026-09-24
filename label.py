"""Label emails one keypress at a time into data/labels.jsonl. Resumable.

python label.py [--target 300]
Keys: a = action, r = review, o = other, x = skip, u = undo, q = quit
"""

import argparse
import json
import random
import sys
import termios
import tty
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

EMAILS = Path("data/emails.jsonl")
LABELS = Path("data/labels.jsonl")
KEYS = {"a": "action", "r": "review", "o": "other"}

console = Console()


def label_order(emails: list[dict], target: int) -> list[dict]:
    """Half from senders you have emailed before, half strangers, interleaved."""
    rng = random.Random(42)
    known = [e for e in emails if e["has_emailed_them"]]
    unknown = [e for e in emails if not e["has_emailed_them"]]
    rng.shuffle(known)
    rng.shuffle(unknown)
    order = []
    while known or unknown:
        for pool in (known, unknown):
            if pool:
                order.append(pool.pop())
    # Short on known senders: the tail is all strangers, which is the best we can do.
    return order[: target * 2]  # spare emails to cover skips


def getch() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1).lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def load_labels() -> list[dict]:
    return [json.loads(l) for l in LABELS.open()] if LABELS.exists() else []


def save_labels(labels: list[dict]) -> None:
    LABELS.write_text("".join(json.dumps(l) + "\n" for l in labels))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=300)
    target = ap.parse_args().target

    emails = [json.loads(l) for l in EMAILS.open()]
    order = label_order(emails, target)
    labels = load_labels()

    while True:
        done = {l["id"] for l in labels}
        counts = Counter(l["category"] for l in labels if "category" in l)
        n = sum(counts.values())
        todo = [e for e in order if e["id"] not in done]
        if n >= target or not todo:
            break
        e = todo[0]
        console.clear()
        known = "[green]emailed before[/]" if e["has_emailed_them"] else "[yellow]stranger[/]"
        console.print(f"[bold]{n}/{target}[/]  action {counts['action']} · review {counts['review']} · other {counts['other']}\n")
        console.print(Panel(
            f"[bold]{e['from_name']}[/] <{e['from_email']}>  {known}\n"
            f"[dim]{e['date']}[/]\n\n[bold]{e['subject']}[/]\n\n{e['body']}",
            width=100,
        ))
        console.print("[bold]a[/] action  [bold]r[/] review  [bold]o[/] other   [dim]x skip · u undo · q quit[/]")

        key = getch()
        if key in KEYS:
            labels.append({"id": e["id"], "category": KEYS[key]})
        elif key == "x":
            labels.append({"id": e["id"], "skipped": True})
        elif key == "u" and labels:
            labels.pop()
        elif key in ("q", "\x03"):
            break
        else:
            continue
        save_labels(labels)

    console.print(f"\nSaved {sum('category' in l for l in labels)} labels to {LABELS}")


if __name__ == "__main__":
    main()
