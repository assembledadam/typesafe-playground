# Demo build brief: one email classifier, three System One backends

Owner: Adam · Written: Wed 23 Sep 2026 · Needed by: **Thu 24 Sep, end of day** (talk is Fri 25 Sep)

Read `jev-talk-research-brief.md` in this folder for background on Jev and System One models. This brief is self-contained for the build.

## 1. What we're building and why

A small Python CLI that sends the same set of emails, with the same questions, to three different "System One" backends. It reports accuracy, latency, cost and a simple calibration check for each one.

It's the live demo in a 10-minute talk. The point it has to make on stage:

- **The only thing that changes between backends is the base URL.** The Jev API is so easy to copy that open and EU-hosted clones speak the same protocol.
- **Where your data runs is a real choice:**
  - **Jev:** US-hosted and rate-limited.
  - **EigenJev:** EU-hosted, in Berlin.
  - **Laya:** runs on the laptop, so no data leaves the room.
- **Calibration is the claim worth testing:** when a backend says it's more than 90% sure, is it right?

Keep it simple and robust. It runs live in front of an audience, so reliability beats features.

## 2. The three backends

| Name in code | What | Where | How to call |
|---|---|---|---|
| `jev` | TypeSafe Jev (`jev-latest`) | US, `https://api.typesafe.ai` | Official SDK, key in `TYPESAFE_API_KEY` |
| `eigenjev` | Eigenwelt Labs EigenJev | EU (Berlin), claimed EU-only inference and zero retention | Same SDK, different base URL and key. **Base URL is behind a sign-in at https://platform.eigenweltlabs.com/eigenjev/docs. Adam to supply it with the key.** |
| `laya` | Laya, open weights (ModernBERT, Apache-2.0) | Local, on Adam's Mac | Run `laya-serve` locally. It speaks `POST /v1/systemone`. See https://github.com/NandhaKishorM/laya |

Optional fourth, only if everything else is done: `kev` (Jared Palmer, https://github.com/jaredpalmer/kev). It runs Kev-4B locally on Apple Silicon via MLX and also serves `/v1/systemone`.

### API reference (Jev)

- Install: `pip install typesafe-sdk` (Python 3.10+)
- Endpoint: `POST {base_url}/v1/systemone`
- Limits:
  - 64k tokens per request (state plus all questions)
  - 32k tokens per question
  - 255 options max per Choice
  - about 1,200 requests/min
- Pricing: $0.042 per million input tokens. Output is free.

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

client = TypeSafeClient()  # reads TYPESAFE_API_KEY
resp = client.system_one(
    state={"email": {"from": "...", "subject": "...", "body": "..."}},
    questions={
        "category": Choice(instructions="...", criteria={"customer": "...", ...}),
        "needs_my_reply": Noul(instructions="..."),
        "urgency": Score(instructions="...", criteria=["...", "...", "..."]),
    },
)
a = resp.answers["category"]
a.choice, a.confidence, a.probabilities   # "customer", 0.94, {...}
resp.answers["needs_my_reply"].noul        # 0.87
resp.answers["urgency"].score              # 1.6
```

**Verify first (day-one spike, 30 minutes max):**
- How the SDK takes a custom base URL: a constructor argument, or a `TYPESAFE_BASE_URL` env var? One open clone's docs say to set `TYPESAFE_BASE_URL`.
- Whether EigenJev and `laya-serve` accept the SDK's requests unchanged.
- Whether the response carries token usage. If not, estimate cost from input size.
- Whether one request can hold questions for many emails (e.g. `category_017`), to show a batch of 100 emails in one call. If it can't, or it's awkward, use a small thread pool of single-email requests. Don't sink time into this.

If a backend isn't compatible with the SDK, write a thin `httpx` client for `/v1/systemone` rather than fighting it.

## 3. Data

### Getting the emails

- Pull about 120 recent emails from Adam's inbox and keep 100 after filtering. Gmail is fine via whatever access is available (Gmail API/MCP, IMAP, or a Google Takeout .mbox Adam exports). Ask Adam which he prefers.
- Keep only these fields:
  - `id`
  - `from_name`
  - `from_domain`
  - `subject`
  - `date`
  - `body`: the first ~600 characters of plain text, with quoted replies and signatures stripped where easy
- Store them in `data/emails.jsonl`.
- **Exclude** anything with obviously sensitive content: payroll, HR, legal, health, bank or card details, passwords, one-time codes. A keyword filter plus Adam skimming the list is enough.

### Privacy

- These are real business emails and one backend is US-hosted. **Get Adam to approve the final 100 before anything is sent to any backend.**
- `data/` must be in `.gitignore`. Never commit emails or keys.
- On screen, show a **redacted** view: sender replaced with a role label such as "Customer A", and no bodies. Add a `--redact` flag, default on.

### Labels (ground truth)

- Build a tiny labelling CLI (`label.py`). It shows one email at a time and records Adam's answers to `data/labels.jsonl`. The target is under 30 minutes for 100 emails, so use single-key answers.
- **Do not pre-fill labels with any model's output.** That would bias the results towards that model.
- Label all three questions per email:
  - `category`: one of the options below
  - `needs_my_reply`: yes or no
  - `urgency`: low, medium or high

## 4. The questions (same for every backend)

Keep them in one file (`questions.py`) so every backend gets identical wording.

- **category** (Choice). Keep it to 6 options, since Laya is weak above about 20:
  - `customer`: a customer or prospect of Claimer writing about their account, a claim or the product
  - `investor_board`: investors, board members or shareholders
  - `cold_outreach`: unsolicited sales, recruiting or partnership pitches
  - `internal`: colleagues at Claimer
  - `newsletter_notification`: newsletters, automated notifications, receipts, alerts
  - `personal`: friends, family, personal admin
- **needs_my_reply** (Noul): "Adam personally needs to reply to or act on this email"
- **urgency** (Score), 3 levels:
  - "Can wait a week or more"
  - "Should be handled in the next day or two"
  - "Needs attention today"

Adam may tweak the wording. Keep the option keys stable.

## 5. What the CLI does

```
python run.py --backend jev|eigenjev|laya|all [--limit 100] [--redact] [--record out/run.json]
python report.py out/*.json   # prints the comparison table
```

For each backend:

1. Send every email with the three questions. Record each answer, its confidence/probabilities, the latency per call and the input tokens (or an estimate).
2. Compare against `labels.jsonl`.
3. Print, live as it runs, one line per email: redacted sender, predicted category, confidence, a tick or cross against the label, and ms. This is what the audience watches, so make it readable in a large terminal font.
4. At the end, print the summary table:

| Backend | Runs in | Accuracy (category) | p50 ms | p95 ms | Cost / 100 emails | Share with conf. > 0.9 | Accuracy when conf. > 0.9 |
|---|---|---|---|---|---|---|---|

Also compute, but don't show by default: accuracy for `needs_my_reply` (Noul above 0.5 counts as yes) and for `urgency` (score rounded to the nearest level).

**Calibration extra (nice to have):** a simple reliability chart for `category`. Bucket the answers by confidence (0.5-0.6, ..., 0.9-1.0) and plot accuracy in each bucket against a diagonal. Save one PNG per backend to `out/`. Adam may use this on a slide, so make it clean, readable and large-font.

## 6. Reliability for a live demo

- Every backend call has a timeout (5 s) and one retry. A failure is logged as an error for that email, never a crash.
- If a backend is unreachable at startup, print a clear one-line message and skip it.
- **Record mode:** `--record` saves every raw request and response. `--replay out/run.json` re-prints a recorded run at the original pace, for use if the venue network fails.
- Laya must work fully offline. Test this with wifi off.
- Cache the Laya model weights locally on Thursday, so nothing downloads on Friday.
- Pin package versions in `requirements.txt`. Use Jev's pinned model version (currently `jev-1.13.0`), not `jev-latest`, so it can't change overnight.

## 7. Deliverables

In this folder (`typesafe-playground`):

- `README.md`: setup in five commands or fewer, and how to run the demo and the replay
- `.env.example`: `TYPESAFE_API_KEY`, `EIGENJEV_API_KEY`, `EIGENJEV_BASE_URL`, `LAYA_BASE_URL` (default `http://localhost:8000` or whatever `laya-serve` uses)
- `.gitignore`: `.env`, `data/`, `out/`, model caches
- `fetch_emails.py`, `label.py`, `questions.py`, `backends.py`, `run.py`, `report.py`
- `out/run-<date>.json` for all three backends, plus the summary table as `out/summary.md`, for the results slide
- A short screen recording of a full run (Adam can record it, but make the output look good for it)

## 8. Acceptance criteria

- [ ] `python run.py --backend all --redact` completes on 100 labelled emails, with every backend listed in the summary table.
- [ ] Swapping backends changes only the base URL and key. Show this in `backends.py`, one small dict, because it goes on a slide.
- [ ] Laya runs with wifi off.
- [ ] `--replay` reproduces the run without network.
- [ ] No email content or key is committed. `git status` is clean of `data/`, `out/` and `.env`.
- [ ] A full live run takes under 90 seconds end to end (it has to fit in a 3-minute demo slot).

## 9. Timeline

| When | What |
|---|---|
| Wed evening | Spike: verify the base URL override on all three backends with one hand-written email. Adam gets the EigenJev key. |
| Thu morning | Fetch and filter emails, Adam approves them, Adam labels them (30 min). |
| Thu midday | Full runs, summary table, calibration chart. |
| Thu afternoon | Record the backup run, offline test, hand the numbers to Adam for the results slide. |

## 10. Open questions for Adam

1. How should the agent access Gmail: API/MCP, IMAP or an .mbox export?
2. The EigenJev base URL and key (from the sign-in-only docs).
3. Should the category list stay as above, or change?
4. Is it OK to send the approved 100 emails to US and EU hosted APIs, or should the Jev run use only the least sensitive categories (newsletters, cold outreach)?

## Sources

- TypeSafe launch post: https://typesafe.ai/blog/introducing-system-one-models-and-jev
- Jev API guide (SDK usage): https://dev.to/valyuai/how-to-use-jev-a-practical-guide-to-typesafes-system-one-model-g5e
- EigenJev: https://platform.eigenweltlabs.com/eigenjev/docs
- Laya: https://github.com/NandhaKishorM/laya
- Kev: https://github.com/jaredpalmer/kev
- Jev on OpenRouter (alternative Jev endpoint if TypeSafe is rate-limiting): https://openrouter.ai/typesafe/jev-1.13
