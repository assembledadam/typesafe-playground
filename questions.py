"""The one question every backend gets, word for word."""

from typesafe_sdk import Choice

CATEGORIES = ("action", "review", "other")

INSTRUCTIONS = (
    "How should Adam, CEO of Claimer, treat `email` in his inbox? "
    "Judge who the sender really is and what they want from Adam."
)

CRITERIA = {
    "action": (
        "Adam personally must reply, decide or do something, and the sender has a real "
        "relationship with Adam or Claimer: customer, investor, colleague, partner or friend. "
        "Unsolicited pitches do not count, even when they ask for a reply, a call or quick thoughts."
    ),
    "review": (
        "Worth Adam reading because it affects Claimer or him, but needs no action from him: "
        "updates, reports, FYIs, replies that close a thread; invoices, receipts and renewals "
        "from suppliers or contractors; account security alerts; scans of his physical post; "
        "online order confirmations."
    ),
    "other": (
        "Safe to ignore or archive: cold outreach, sales, recruiting or partnership pitches, "
        "newsletters, marketing, and generic automated notifications such as customer-portal "
        "alerts ('A task has been assigned to you', 'Extraction comparison ready')."
    ),
}

HISTORY_NOTE = (
    " `sender_history.adam_has_emailed_them` says whether Adam has ever sent an email "
    "to this sender; a stranger asking for a reply is usually a cold pitch."
)

PROFILE_NOTE = " `adam` describes what Adam cares about and ignores, and who he works with."

# Adam's own words, split into lists so each item stands alone.
ADAM = {
    "role": "CEO of Claimer (R&D tax-credit software)",
    "cares_about": [
        "customer requests",
        "overdue payments or notices",
        "customer support tickets",
        "investors",
        "expense receipts, invoices and renewals",
        "emails from named HMRC individuals (not general HMRC notices)",
    ],
    "ignores": [
        "generic customer-portal notifications (e.g. 'A task has been assigned to you', 'Extraction comparison ready')",
        "sales emails",
        "other automated notifications",
        "generic industry newsletters",
        "partnership pitches",
    ],
    "colleagues": ["Usman Mahomed", "Paul Ubas", "Oliwia Motley", "Monalisa Baltatescu"],
}

CATEGORY = Choice(instructions=INSTRUCTIONS, criteria=CRITERIA)


def build(email: dict, history: bool, profile: bool = False) -> tuple[dict, dict]:
    """State and questions for one email."""
    state = {
        "email": {
            "from": f"{email['from_name']} <{email['from_domain']}>",
            "subject": email["subject"],
            "date": email["date"],
            "body": email["body"],
        }
    }
    instructions = INSTRUCTIONS
    if history:
        state["sender_history"] = {"adam_has_emailed_them": email["adam_has_emailed_them"]}
        instructions += HISTORY_NOTE
    if profile:
        state["adam"] = ADAM
        instructions += PROFILE_NOTE
    return state, {"category": Choice(instructions=instructions, criteria=CRITERIA)}
