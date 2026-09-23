"""Day-one spike: one hand-written email to each backend. Throwaway."""

import sys
import time

from backends import BACKENDS, client
from questions import build

EMAILS = [
    {"from_name": "Sam Patel", "from_domain": "growthleads.io", "subject": "Quick question, Adam",
     "date": "2026-09-22", "adam_has_emailed_them": False,
     "body": "Hi Adam, I noticed Claimer is scaling fast. We help insurtechs book 30+ meetings a month. "
             "Can you reply with a time that works for a 15 min call this week?"},
    {"from_name": "Priya Shah", "from_domain": "bigcustomer.co.uk", "subject": "Renewal terms",
     "date": "2026-09-22", "adam_has_emailed_them": True,
     "body": "Adam, our board meets Thursday. Can you confirm whether the 2027 pricing we discussed holds? "
             "I need your answer by Wednesday to include it."},
]

for name in sys.argv[1:] or BACKENDS:
    print(f"\n== {name} ({BACKENDS[name]['base_url']})")
    try:
        c = client(name)
    except Exception as e:
        print("  client error:", repr(e))
        continue
    for email in EMAILS:
        for hist in (False, True):
            state, qs = build(email, history=hist)
            t = time.perf_counter()
            try:
                r = c.system_one(state, qs)
            except Exception as e:
                print(f"  {email['from_domain']:20} hist={hist!s:5} ERROR {e!r}")
                continue
            a = r.answers["category"]
            ms = (time.perf_counter() - t) * 1000
            probs = {k: round(v, 3) for k, v in a.probabilities.items()}
            print(f"  {email['from_domain']:20} hist={hist!s:5} {a.choice:7} conf={a.confidence:.3f} "
                  f"{probs} usage={r.usage} model={r.model} {ms:.0f}ms")
