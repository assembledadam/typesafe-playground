# One email classifier, three System One backends

The same emails and question (`action` / `review` / `other`) go to Jev (US), EigenJev (EU) and Laya (on this laptop). Only the base URL, key and model name change: see `backends.py`.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # fill in keys
.venv/bin/python fetch_emails.py           # ~1000 received emails via the gws CLI -> data/
.venv/bin/python label.py                  # a/r/o per email, 300 target
LAYA_HOST=127.0.0.1 LAYA_DEVICE=mps LAYA_MODELS=english LAYA_PRELOAD=1 HF_HOME=.cache/huggingface .venv/bin/laya-serve
```

## Demo

```bash
.venv/bin/python server.py                          # web UI: http://localhost:8080 (press r to run)
# backup with no network: http://localhost:8080/?replay=<recording>&limit=100

.venv/bin/python run.py --limit 100                 # all backends, redacted, recorded to out/
.venv/bin/python run.py --limit 100 --history       # + "has Adam emailed this sender before?"
.venv/bin/python run.py --replay out/run-XXXX.json  # no network: re-prints a recorded run at its original pace
```

## Results

```bash
.venv/bin/python report.py out/run-*.json --charts --agreement   # table, out/summary.md, calibration PNGs
.venv/bin/python run.py --unlabelled                            # all ~1000 emails: latency, cost, agreement
```

- **Balanced acc.**: mean of per-category accuracy, so the many easy `other` emails don't flatter anyone.
- **Conf. > 0.9**: the backend's own `confidence` field (distribution concentration, not a probability).
- **Calibration chart**: x = top option's probability, y = share actually correct.
- **Cold → action**: strangers labelled `other` that the backend marked `action`.

For Laya offline, add `HF_HUB_OFFLINE=1` to the `laya-serve` line.
