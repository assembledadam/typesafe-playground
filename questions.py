"""The one question every backend gets, word for word. Personalised from profile.json."""

import json
from pathlib import Path

from typesafe_sdk import Choice

CATEGORIES = ("action", "review", "other")

# Your own profile.json (git-ignored); falls back to the example so the repo runs out of the box.
PROFILE = json.loads((Path("profile.json") if Path("profile.json").exists() else Path("profile.example.json")).read_text())
NAME, COMPANY = PROFILE["name"], PROFILE["company"]

INSTRUCTIONS = (
    f"How should {NAME}, {PROFILE['role']}, treat `email` in their inbox? "
    f"Judge who the sender really is and what they want from {NAME}."
)

CRITERIA = {
    "action": (
        f"{NAME} personally must reply, decide or do something, and the sender has a real "
        f"relationship with {NAME} or {COMPANY}: customer, investor, colleague, partner or friend. "
        "Unsolicited pitches do not count, even when they ask for a reply, a call or quick thoughts."
    ),
    "review": (
        f"Worth {NAME} reading because it affects {COMPANY} or them, but needs no action from them: "
        "updates, reports, FYIs, replies that close a thread; invoices, receipts and renewals "
        f"from suppliers or contractors; account security alerts; scans of {NAME}'s physical post; "
        "online order confirmations."
    ),
    "other": (
        "Safe to ignore or archive: cold outreach, sales, recruiting or partnership pitches, "
        "newsletters, marketing, and generic automated notifications such as customer-portal "
        "alerts ('A task has been assigned to you')."
    ),
}

HISTORY_NOTE = (
    f" `sender_history.has_emailed_them` says whether {NAME} has ever sent an email "
    "to this sender; a stranger asking for a reply is usually a cold pitch."
)

PROFILE_NOTE = f" `profile` describes what {NAME} cares about and ignores, and who they work with."

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
        state["sender_history"] = {"has_emailed_them": email["has_emailed_them"]}
        instructions += HISTORY_NOTE
    if profile:
        state["profile"] = {k: PROFILE[k] for k in ("role", "cares_about", "ignores", "colleagues")}
        instructions += PROFILE_NOTE
    return state, {"category": Choice(instructions=instructions, criteria=CRITERIA)}
