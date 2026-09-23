"""The one question every backend gets, word for word."""

from typesafe_sdk import Choice

CATEGORIES = ("action", "review", "other")

CATEGORY = Choice(
    instructions=(
        "How should Adam, CEO of Claimer, treat `email` in his inbox? "
        "Judge who the sender really is and what they want from Adam."
    ),
    criteria={
        "action": (
            "Adam personally must reply, decide or do something, and the sender has a real "
            "relationship with Adam or Claimer: customer, investor, colleague, partner or friend. "
            "Unsolicited pitches do not count, even when they ask for a reply, a call or quick thoughts."
        ),
        "review": (
            "Worth Adam reading because it affects Claimer or him, but needs no action from him: "
            "updates, reports, FYIs, replies that close a thread."
        ),
        "other": (
            "Safe to ignore or archive: cold outreach, sales, recruiting or partnership pitches, "
            "newsletters, marketing, automated notifications, receipts."
        ),
    },
)

HISTORY_NOTE = (
    " `sender_history.adam_has_emailed_them` says whether Adam has ever sent an email "
    "to this sender; a stranger asking for a reply is usually a cold pitch."
)

CATEGORY_WITH_HISTORY = Choice(
    instructions=CATEGORY.instructions + HISTORY_NOTE,
    criteria=CATEGORY.criteria,
)


def build(email: dict, with_history: bool) -> tuple[dict, dict]:
    """State and questions for one email."""
    state = {
        "email": {
            "from": f"{email['from_name']} <{email['from_domain']}>",
            "subject": email["subject"],
            "date": email["date"],
            "body": email["body"],
        }
    }
    if with_history:
        state["sender_history"] = {"adam_has_emailed_them": email["adam_has_emailed_them"]}
        return state, {"category": CATEGORY_WITH_HISTORY}
    return state, {"category": CATEGORY}
