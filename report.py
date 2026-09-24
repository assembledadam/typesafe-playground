"""Summary table, calibration charts and backend agreement from recorded runs.

python report.py out/*.json [--charts] [--agreement]
"""

import argparse
import itertools
import json
import statistics
from pathlib import Path

from rich.console import Console
from rich.table import Table

from backends import PRICE_PER_M_INPUT
from questions import CATEGORIES

console = Console()
OUT = Path("out")


def load(paths: list[str]) -> list[dict]:
    return [run for p in paths for run in json.loads(Path(p).read_text())["runs"]]


def run_name(run: dict) -> str:
    return run["backend"] + (" +history" if run["history"] else "") + (" +profile" if run.get("profile") else "")


def answer(rec: dict) -> dict | None:
    return None if rec.get("error") else rec["response"]["answers"]["category"]


def pct(x: float | None) -> str:
    return "–" if x is None else f"{x:.0%}"


def summarise(run: dict) -> dict:
    recs = run["records"]
    ok = [r for r in recs if not r.get("error")]
    labelled = [r for r in ok if r.get("label")]
    right = lambda r: answer(r)["choice"] == r["label"]
    sure = [r for r in labelled if answer(r)["confidence"] > 0.9]
    recalls = [
        sum(map(right, rows)) / len(rows)
        for c in CATEGORIES
        if (rows := [r for r in labelled if r["label"] == c])
    ]
    # Cold emails: strangers you labelled as ignorable. How many does the backend flag as action?
    cold = [r for r in labelled if r["label"] == "other" and not r["known_sender"]]
    ms = sorted(r["ms"] for r in ok)
    price = PRICE_PER_M_INPUT.get(run["backend"])
    tokens = statistics.mean(r["response"]["usage"]["input_tokens"] for r in ok) if ok else 0
    return {
        "name": run_name(run),
        "runs_in": run["runs_in"],
        "n": len(recs),
        "errors": len(recs) - len(ok),
        "accuracy": sum(map(right, labelled)) / len(labelled) if labelled else None,
        "balanced": statistics.mean(recalls) if recalls else None,
        "p50": ms[len(ms) // 2] if ms else None,
        "p95": ms[int(len(ms) * 0.95)] if ms else None,
        "cost_100": None if price is None else tokens * 100 * price / 1e6,
        "share_sure": len([r for r in ok if answer(r)["confidence"] > 0.9]) / len(ok) if ok else None,
        "acc_sure": sum(map(right, sure)) / len(sure) if sure else None,
        "cold_to_action": sum(answer(r)["choice"] == "action" for r in cold) / len(cold) if cold else None,
    }


def cost(s: dict) -> str:
    if s["runs_in"] == "This laptop":
        return "$0 (local)"
    if s["cost_100"] == 0:
        return "$0 (free for now)"
    return "unknown" if s["cost_100"] is None else f"${s['cost_100']:.4f}"


COLUMNS = [
    ("Backend", lambda s: s["name"]),
    ("Runs in", lambda s: s["runs_in"]),
    ("Accuracy", lambda s: pct(s["accuracy"])),
    ("Balanced acc.", lambda s: pct(s["balanced"])),
    ("p50 ms", lambda s: f"{s['p50']:.0f}" if s["p50"] else "–"),
    ("p95 ms", lambda s: f"{s['p95']:.0f}" if s["p95"] else "–"),
    ("Cost / 100 emails", cost),
    ("Conf. > 0.9", lambda s: pct(s["share_sure"])),
    ("Acc. when conf. > 0.9", lambda s: pct(s["acc_sure"])),
    ("Cold → action", lambda s: pct(s["cold_to_action"])),
    ("Errors", lambda s: f"{s['errors']}/{s['n']}"),
]


def print_table(summaries: list[dict]) -> None:
    t = Table(title="Email triage: action / review / other", title_style="bold")
    for name, _ in COLUMNS:
        t.add_column(name, justify="left" if name in ("Backend", "Runs in") else "right")
    for s in summaries:
        t.add_row(*(fmt(s) for _, fmt in COLUMNS))
    console.print(t)


def markdown(summaries: list[dict]) -> str:
    head = "| " + " | ".join(n for n, _ in COLUMNS) + " |"
    sep = "|" + "---|" * len(COLUMNS)
    rows = ["| " + " | ".join(fmt(s) for _, fmt in COLUMNS) + " |" for s in summaries]
    return "\n".join([head, sep, *rows]) + "\n"


def agreement(runs: list[dict]) -> str:
    """Share of emails where two backends pick the same category. Needs no labels."""
    choices = {
        run_name(r): {rec["id"]: answer(rec)["choice"] for rec in r["records"] if answer(rec)} for r in runs
    }
    lines = []
    for a, b in itertools.combinations(choices, 2):
        both = choices[a].keys() & choices[b].keys()
        if both:
            same = sum(choices[a][i] == choices[b][i] for i in both) / len(both)
            lines.append(f"{a} vs {b}: {same:.0%} agree ({len(both)} emails)")
    return "\n".join(lines)


def calibration_chart(run: dict) -> Path | None:
    """Accuracy per bucket of top-option probability, against the diagonal."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labelled = [(max(a["probabilities"].values()), a["choice"] == r["label"])
                for r in run["records"] if (a := answer(r)) and r.get("label")]
    if not labelled:
        return None
    edges = [1 / 3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]
    xs, ys, ns = [], [], []
    for lo, hi in zip(edges, edges[1:]):
        bucket = [(p, ok) for p, ok in labelled if lo <= p < hi]
        if bucket:
            xs.append(statistics.mean(p for p, _ in bucket))
            ys.append(sum(ok for _, ok in bucket) / len(bucket))
            ns.append(len(bucket))

    plt.rcParams.update({"font.size": 20})
    fig, ax = plt.subplots(figsize=(9, 8), dpi=150)
    ax.plot([0, 1], [0, 1], "--", color="grey", lw=2, label="Perfectly calibrated")
    ax.plot(xs, ys, "o-", color="#2563eb", lw=4, ms=12, label=run_name(run))
    for x, y, n in zip(xs, ys, ns):
        ax.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(0, 14), ha="center", fontsize=14)
    ax.set(xlim=(0.3, 1.02), ylim=(0, 1.05), xlabel="Model's top probability", ylabel="Actually correct")
    ax.set_title(f"{run_name(run)} · {run['runs_in']}", fontweight="bold")
    ax.legend(loc="upper left", fontsize=15, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = OUT / f"calibration-{run_name(run).replace(' +', '-')}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--charts", action="store_true", help="save calibration PNGs to out/")
    ap.add_argument("--agreement", action="store_true", help="print how often backends agree")
    args = ap.parse_args()

    runs = load(args.paths)
    summaries = [summarise(r) for r in runs]
    print_table(summaries)
    OUT.mkdir(exist_ok=True)
    (OUT / "summary.md").write_text(markdown(summaries))
    console.print(f"[dim]wrote {OUT / 'summary.md'}[/]")
    if args.agreement:
        console.print(agreement(runs))
    if args.charts:
        for r in runs:
            if path := calibration_chart(r):
                console.print(f"[dim]wrote {path}[/]")


if __name__ == "__main__":
    main()
