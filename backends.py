"""Three System One backends. Same SDK, same questions; only where it points changes."""

import os

from dotenv import load_dotenv
from typesafe_sdk import RetryPolicy, TypeSafeClient

load_dotenv()

BACKENDS = {
    "jev":      {"base_url": "https://api.typesafe.ai",       "key": "TYPESAFE_API_KEY", "runs_in": "US"},
    "eigenjev": {"base_url": os.getenv("EIGENJEV_BASE_URL"),  "key": "EIGENJEV_API_KEY", "runs_in": "EU (Berlin)"},
    "laya":     {"base_url": os.getenv("LAYA_BASE_URL", "http://localhost:8000"), "key": None, "runs_in": "This laptop"},
}

# Pinned so nothing changes overnight. EigenJev keys only accept "jev-latest" (serves openjev-0.1).
MODELS = {"jev": "jev-1.13.0", "eigenjev": "jev-latest", "laya": "english"}

PRICE_PER_M_INPUT = {"jev": 0.042, "eigenjev": None, "laya": 0.0}  # EigenJev price unknown


def client(name: str) -> TypeSafeClient:
    b = BACKENDS[name]
    key = os.getenv(b["key"]) if b["key"] else "local"
    # Missing values would silently fall back to the SDK's defaults, i.e. Jev.
    if not b["base_url"] or not key:
        raise RuntimeError(f"{name}: base URL or {b['key']} not set in .env")
    return TypeSafeClient(
        base_url=b["base_url"],
        api_key=key,
        model=MODELS[name],
        timeout=5.0,
        retry=RetryPolicy(max_retries=1, backoff_initial=0.2),
    )
