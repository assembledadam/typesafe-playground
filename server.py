"""Web UI for the demo: three backends race side by side, streamed live to the browser.

.venv/bin/python server.py   ->  http://localhost:8080
"""

import json
import time
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

import report
from backends import BACKENDS, MODELS, PRICE_PER_M_INPUT
from run import connect, load_emails, new_run, redacted_names, stream

app = FastAPI()
OUT = Path("out")


def event(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def for_screen(rec: dict, index: dict, emails: dict, redact: bool) -> dict:
    """The fields the browser needs; no bodies, and no names or subjects when redacted."""
    e = emails[rec["id"]]
    out = {
        "i": index[rec["id"]],
        "who": rec["who_redacted"] if redact else rec["who"],
        "subject": None if redact else e["subject"],
        "label": rec["label"],
        "ms": rec["ms"],
        "error": rec.get("error"),
    }
    if not rec.get("error"):
        a = rec["response"]["answers"]["category"]
        out |= {"choice": a["choice"], "confidence": a["confidence"], "probabilities": a["probabilities"],
                "tokens": rec["response"]["usage"]["input_tokens"]}
    return out


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/api/config")
def config():
    return {
        "backends": [
            {"name": n, "runs_in": b["runs_in"], "base_url": b["base_url"], "model": MODELS[n],
             "price": PRICE_PER_M_INPUT[n]}
            for n, b in BACKENDS.items()
        ],
        "labelled": len(load_emails(False, None)),
        "recordings": sorted({p.stem.split("__")[0] for p in OUT.glob("*.json")}, reverse=True),
    }


@app.get("/api/run")
def run(backend: str, limit: int = 100, history: bool = False, profile: bool = False, redact: bool = True, session: str = ""):
    if backend not in BACKENDS:
        raise HTTPException(404)
    emails = load_emails(False, limit)
    names = redacted_names(emails)
    index = {e["id"]: i for i, e in enumerate(emails)}
    by_id = {e["id"]: e for e in emails}
    session = session or f"web-{datetime.now():%Y%m%d-%H%M%S}"

    def events():
        yield event("start", {"total": len(emails)})
        try:
            c = connect(backend)
        except Exception as e:
            yield event("failed", {"error": f"{type(e).__name__}: {str(e)[:120]}"})
            return
        rec_run = new_run(backend, history, profile)
        for rec in stream(c, backend, emails, history, profile, names):
            rec_run["records"].append(rec)
            yield event("result", for_screen(rec, index, by_id, redact))
        # One file per backend so three parallel streams never write the same file.
        OUT.mkdir(exist_ok=True)
        (OUT / f"{session}__{backend}.json").write_text(json.dumps({"runs": [rec_run]}, ensure_ascii=False))
        yield event("done", {"session": session})

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/replay")
def replay(recording: str, backend: str, redact: bool = True):
    """Re-stream a recorded run at its original pace. No network needed."""
    runs = [r for p in OUT.glob(f"{recording}*.json") for r in report.load([str(p)]) if r["backend"] == backend]
    if not runs:
        raise HTTPException(404, f"no {backend} run in {recording}")
    run = runs[0]
    emails = {e["id"]: e for e in map(json.loads, Path("data/emails.jsonl").open())}
    # Same email, same square in every column: order by labelling order, not completion.
    label_pos = {e["id"]: i for i, e in enumerate(load_emails(False, None))}
    ordered = sorted(run["records"], key=lambda r: label_pos.get(r["id"], len(label_pos)))
    index = {r["id"]: i for i, r in enumerate(ordered)}

    def events():
        yield event("start", {"total": len(run["records"])})
        start = time.perf_counter()
        for rec in sorted(run["records"], key=lambda r: r["t"]):
            time.sleep(max(0.0, rec["t"] - (time.perf_counter() - start)))
            yield event("result", for_screen(rec, index, emails, redact))
        yield event("done", {"session": recording})

    return StreamingResponse(events(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="warning")
