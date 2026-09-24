"""Send the same emails and question to each backend; show answers live, then the summary.

python run.py --backend jev|eigenjev|kev|all [--limit 100] [--history] [--profile] [--no-redact] [--unlabelled]
python run.py --replay out/run-....json     # re-print a recorded run at its original pace, no network
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Iterator

from rich.console import Console
from rich.rule import Rule

import report
from backends import BACKENDS, MODELS, client
from questions import CATEGORY, NAME, PROFILE, build

console = Console(highlight=False)
EMAILS = Path("data/emails.jsonl")
LABELS = Path("data/labels.jsonl")
WORKERS = {"kev": 1, "jev": 4}  # Local models: parallel only queues. Jev: throttles bursts.
COLOURS = {"action": "bold yellow", "review": "cyan", "other": "dim"}


def load_emails(unlabelled: bool, limit: int | None) -> list[dict]:
    emails = {e["id"]: e for e in map(json.loads, EMAILS.open())}
    if unlabelled:
        chosen = [dict(e, label=None) for e in emails.values()]
    else:
        labels = [l for l in map(json.loads, LABELS.open()) if "category" in l]
        chosen = [dict(emails[l["id"]], label=l["category"]) for l in labels]
    return chosen[:limit]


def redacted_names(emails: list[dict]) -> dict[str, str]:
    """Sender -> role label for the screen, e.g. 'Stranger 12'."""
    names, counts = {}, {}
    for e in emails:
        if e["from_email"] in names:
            continue
        role = ("Colleague" if e["from_domain"] == PROFILE["company_domain"]
                else "Contact" if e["has_emailed_them"] else "Stranger")
        counts[role] = counts.get(role, 0) + 1
        names[e["from_email"]] = f"{role} {counts[role]}"
    return names


def line(rec: dict, redact: bool) -> str:
    who = (rec["who_redacted"] if redact else rec["who"])[:22]
    if rec.get("error"):
        return f"  {who:<22}  [red]error: {rec['error'][:50]}[/]"
    a = rec["response"]["answers"]["category"]
    mark = "  " if rec["label"] is None else ("[green]✓[/]" if a["choice"] == rec["label"] else "[red]✗[/]")
    colour = COLOURS[a["choice"]]
    return f"  {who:<22}  [{colour}]{a['choice']:<7}[/]  {a['confidence']:.2f}  {mark}  [dim]{rec['ms']:>5.0f} ms[/]"


def header(run: dict) -> None:
    extra = (" · + sender history" if run["history"] else "") + (" · + profile" if run.get("profile") else "")
    console.print(Rule(f"[bold]{run['backend']}[/] · {run['runs_in']} · {run['model']}{extra}"))


def ask(c, email: dict, history: bool, profile: bool, t0: float) -> dict:
    state, questions = build(email, history, profile)
    rec = {
        "id": email["id"],
        "label": email["label"],
        "known_sender": email["has_emailed_them"],
        "request": {"state": state, "questions": {k: q.model_dump(mode="json") for k, q in questions.items()}},
    }
    start = time.perf_counter()
    try:
        rec["response"] = c.system_one(state, questions).model_dump(mode="json")
    except Exception as e:  # a failed email is logged, never a crash
        rec["error"] = f"{type(e).__name__}: {e}"
    end = time.perf_counter()
    rec["ms"] = (end - start) * 1000
    rec["t"] = end - t0
    return rec


def connect(name: str):
    """Client for a backend, or raise if it's misconfigured or unreachable."""
    c = client(name)
    c.system_one({"text": "ping"}, {"category": CATEGORY})
    return c


def stream(c, name: str, emails: list[dict], history: bool, profile: bool, names: dict) -> Iterator[dict]:
    """Records in completion order; shared by the terminal and the web UI."""
    t0 = time.perf_counter()
    by_id = {e["id"]: e for e in emails}
    with ThreadPoolExecutor(WORKERS.get(name, 8)) as pool:
        futures = [pool.submit(ask, c, e, history, profile, t0) for e in emails]
        for f in as_completed(futures):
            rec = f.result()
            e = by_id[rec["id"]]
            rec["who"], rec["who_redacted"] = e["from_name"], names[e["from_email"]]
            yield rec


def new_run(name: str, history: bool, profile: bool) -> dict:
    return {"backend": name, "runs_in": BACKENDS[name]["runs_in"], "model": MODELS[name],
            "history": history, "profile": profile, "records": []}


def run_backend(name: str, emails: list[dict], history: bool, profile: bool, redact: bool, names: dict) -> dict | None:
    try:
        c = connect(name)
    except Exception as e:
        console.print(f"[red]Skipping {name}: {type(e).__name__}: {str(e)[:80]}[/]")
        return None

    run = new_run(name, history, profile)
    header(run)
    t0 = time.perf_counter()
    for rec in stream(c, name, emails, history, profile, names):
        run["records"].append(rec)
        console.print(line(rec, redact))
    console.print(f"[dim]{len(emails)} emails in {time.perf_counter() - t0:.1f} s[/]\n")
    return run


def replay(path: str, redact: bool) -> list[dict]:
    runs = report.load([path])
    for run in runs:
        header(run)
        start = time.perf_counter()
        for rec in sorted(run["records"], key=lambda r: r["t"]):
            time.sleep(max(0.0, rec["t"] - (time.perf_counter() - start)))
            console.print(line(rec, redact))
        console.print(f"[dim]{len(run['records'])} emails in {max(r['t'] for r in run['records']):.1f} s[/]\n")
    return runs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=[*BACKENDS, "all"], default="all")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--history", action="store_true", help=f"tell backends whether {NAME} has emailed the sender")
    ap.add_argument("--profile", action="store_true", help=f"tell backends what {NAME} cares about and who they work with (profile.json)")
    ap.add_argument("--redact", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--unlabelled", action="store_true", help="all fetched emails, no accuracy")
    ap.add_argument("--record", help="where to save the run (default out/run-<timestamp>.json)")
    ap.add_argument("--replay", help="re-print a recorded run without network")
    args = ap.parse_args()

    if args.replay:
        runs = replay(args.replay, args.redact)
    else:
        emails = load_emails(args.unlabelled, args.limit)
        names = redacted_names(emails)
        backends = list(BACKENDS) if args.backend == "all" else [args.backend]
        runs = [r for n in backends if (r := run_backend(n, emails, args.history, args.profile, args.redact, names))]
        out = Path(args.record or f"out/run-{datetime.now():%Y%m%d-%H%M%S}.json")
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps({"runs": runs}, ensure_ascii=False))
        console.print(f"[dim]recorded to {out}[/]")

    report.print_table([report.summarise(r) for r in runs])


if __name__ == "__main__":
    main()
