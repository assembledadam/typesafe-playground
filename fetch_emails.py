"""Pull recent received emails from Gmail via the gws CLI into data/emails.jsonl.

python fetch_emails.py [--target 1300]
"""

import argparse
import json
import re
import subprocess
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from pathlib import Path

from questions import PROFILE

QUERY = "-in:sent -in:chats -in:drafts -from:me"
PER_SENDER_CAP = 5
BODY_CHARS = 600
OUT = Path("data/emails.jsonl")
RAW = Path("data/raw")  # one JSON per message, so reruns skip Gmail


def gws(*args: str) -> dict:
    # Gmail caps search cost per user per minute; wait it out rather than fail the whole fetch.
    for attempt in range(6):
        res = subprocess.run(["gws", "gmail", *args], capture_output=True, text=True)
        if res.returncode == 0:
            return json.loads(res.stdout)
        if "rateLimitExceeded" not in res.stdout + res.stderr:
            raise subprocess.CalledProcessError(res.returncode, res.args, res.stdout, res.stderr)
        time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"Gmail quota still exceeded: {args}")


def list_ids(limit: int) -> list[str]:
    ids, token = [], None
    while len(ids) < limit:
        params = {"userId": "me", "q": QUERY, "maxResults": 500, **({"pageToken": token} if token else {})}
        page = gws("users", "messages", "list", "--params", json.dumps(params))
        ids += [m["id"] for m in page.get("messages", [])]
        token = page.get("nextPageToken")
        if not token:
            break
    return ids[:limit]


def sender(msg: dict) -> dict:
    # Google Group forwards ("X via Sales") carry the real sender in Reply-To.
    s = msg["from"]
    if " via " in (s.get("name") or "") and msg.get("reply_to"):
        s = msg["reply_to"][0]
    return {"name": (s.get("name") or "").strip("'\" ") or s["email"], "email": s["email"].lower()}


QUOTE_START = re.compile(r"^(On .+wrote:|-----Original Message-----|From: .+|-- ?)$", re.M)


def clean_body(msg: dict) -> str:
    text = msg.get("body_text") or re.sub(r"<[^>]+>", " ", msg.get("body_html") or "")
    text = QUOTE_START.split(text, maxsplit=1)[0]
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))
    text = re.sub(r"\(\s*https?://\S+\s*\)|https?://\S+", "", text)
    # Marketing mail pads previews with invisible characters (zero-width, combining joiners).
    text = "".join(c for c in text if unicodedata.category(c) not in ("Cf", "Mn"))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:BODY_CHARS]


def read(msg_id: str) -> dict | None:
    cached = RAW / f"{msg_id}.json"
    if cached.exists():
        msg = json.loads(cached.read_text())
    else:
        try:
            msg = gws("+read", "--id", msg_id, "--headers", "--format", "json")
        except (subprocess.CalledProcessError, RuntimeError):
            return None
        cached.write_text(json.dumps(msg))
    s = sender(msg)
    body = clean_body(msg)
    if not body:
        return None
    sent_at = parsedate_to_datetime(msg["date"])
    return {
        "id": msg_id,
        "from_name": s["name"],
        "from_email": s["email"],
        "from_domain": s["email"].split("@")[-1],
        "subject": msg.get("subject") or "",
        "date": sent_at.date().isoformat(),
        "timestamp": int(sent_at.timestamp()),
        "body": body,
    }


# An out-of-office auto-replies to everyone, including cold pitches; that is not knowing them.
NOT_AUTO_REPLY = f'-subject:"{PROFILE["auto_reply_subject"]}"'


def sent_to_before(address: str, timestamp: int) -> bool:
    q = f"in:sent to:{address} before:{timestamp} {NOT_AUTO_REPLY}"
    res = gws("users", "messages", "list", "--params", json.dumps({"userId": "me", "q": q, "maxResults": 1}))
    return bool(res.get("messages"))


def mark_history(emails: list[dict]) -> None:
    """Have you emailed this sender BEFORE this email arrived? A later reply would leak the label.

    One search per sender at their latest email; per-email searches only where that says yes.
    """
    by_sender: dict[str, list[dict]] = {}
    for e in emails:
        by_sender.setdefault(e["from_email"], []).append(e)

    def check(group: list[dict]) -> None:
        latest = max(group, key=lambda e: e["timestamp"])
        if not sent_to_before(latest["from_email"], latest["timestamp"]):
            for e in group:
                e["has_emailed_them"] = False
            return
        for e in group:
            e["has_emailed_them"] = e is latest or sent_to_before(e["from_email"], e["timestamp"])

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(check, by_sender.values()))


def write(emails: list[dict]) -> None:
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in emails))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1300)
    ap.add_argument("--history-only", action="store_true", help="recompute has_emailed_them on the existing file")
    args = ap.parse_args()

    if args.history_only:
        emails = [json.loads(l) for l in OUT.open()]
        before = sum(e["has_emailed_them"] for e in emails)
        mark_history(emails)
        write(emails)
        print(f"previously emailed: {before} -> {sum(e['has_emailed_them'] for e in emails)}")
        return

    RAW.mkdir(parents=True, exist_ok=True)
    ids = list_ids(int(args.target * 1.6))
    print(f"listed {len(ids)} messages", flush=True)
    with ThreadPoolExecutor(3) as pool:
        fetched = [m for m in pool.map(read, ids) if m]

    per_sender: dict[str, int] = {}
    kept = []
    for m in fetched:  # newest first
        if per_sender.get(m["from_email"], 0) < PER_SENDER_CAP:
            per_sender[m["from_email"]] = per_sender.get(m["from_email"], 0) + 1
            kept.append(m)
    kept = kept[: args.target]

    mark_history(kept)

    write(kept)
    known = sum(m["has_emailed_them"] for m in kept)
    print(f"fetched {len(fetched)}, kept {len(kept)} ({len(per_sender)} senders, {known} previously emailed) -> {OUT}")


if __name__ == "__main__":
    main()
