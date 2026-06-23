"""
Prototype configuration ("Path A": autonomous agents).

Secrets should come from environment variables (.env). The defaults below are
INVALID placeholders kept only for illustration — never store real tokens in
the code or repository.

Roles:
  * Analyst (аналитик)  — states the collection task and receives the report.
  * Manager (менеджер)  — provides the budgets for a given channel.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# ======== Proxy (needed to reach Telegram on some networks) ========
USE_PROXY = _flag("USE_PROXY", True)
PROXY_URL = os.getenv("PROXY_URL", "socks5://127.0.0.1:10808")

# ======== Telegram (example, invalid token) ========
TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    "8433165530:AAFBX_Vzo5kBkVP2MQ7ivjfHcp7rCN-1s-c",  # example, invalid
)

# ======== LLM (Mistral via the OpenAI-compatible client) ========
# USE_LLM=False -> the prototype runs offline on a rule-based parser
# (handy for the defense). The LLM prompts operate on Russian input, so they
# are intentionally kept in Russian.
USE_LLM = _flag("USE_LLM", False)
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "your-mistral-key-here")  # example
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.mistral.ai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral-small-latest")

# ======== Demo: the analyst's Telegram id ========
# In the single-account demo the managers share this id, so the whole cycle
# can be shown from one account.
ANALYST_CHAT_ID = int(os.getenv("ANALYST_CHAT_ID", "1057293934"))

VALID_GEOS = {"BY", "KZ", "RU"}

# ======== Agent behaviour ========
# How many times a collector re-asks when the answer cannot be parsed
COLLECTOR_MAX_RETRIES = int(os.getenv("COLLECTOR_MAX_RETRIES", "2"))
# Deadline timings (seconds). Kept small so the reminder/escalation is visible
# during the defense; in production these would be hours/days.
REMINDER_AFTER_SEC = int(os.getenv("REMINDER_AFTER_SEC", "60"))
ESCALATE_AFTER_SEC = int(os.getenv("ESCALATE_AFTER_SEC", "120"))
# Validator anomaly threshold: relative deviation from last month.
# 0.5 = a change larger than 50% is treated as suspicious and challenged.
ANOMALY_THRESHOLD = float(os.getenv("ANOMALY_THRESHOLD", "0.5"))

# ======== GEO -> channels -> candidate managers ========
# A single (GEO, channel) pair may have SEVERAL candidate managers with
# different reliability. The coordinator runs a small tender (Contract Net):
# it picks the most reliable / least loaded manager, the rest become backups
# (used if the primary does not answer before the deadline).
# Manager names are user-facing, so they stay in Russian.
GEO_STRUCTURE = {
    "BY": {
        "channels": {
            "Mobile": [
                {"name": "Марина", "chat_id": ANALYST_CHAT_ID, "reliability": 0.9},
                {"name": "Ольга",  "chat_id": ANALYST_CHAT_ID, "reliability": 0.6},
            ],
            "Media": [
                {"name": "Екатерина", "chat_id": ANALYST_CHAT_ID, "reliability": 0.8},
            ],
        },
    },
    "KZ": {
        "channels": {
            "Mobile": [
                {"name": "Константин", "chat_id": ANALYST_CHAT_ID, "reliability": 0.7},
                {"name": "Дамир",      "chat_id": ANALYST_CHAT_ID, "reliability": 0.85},
            ],
            "Affiliate": [
                {"name": "Анастасия", "chat_id": ANALYST_CHAT_ID, "reliability": 0.75},
            ],
        },
    },
}

# All channel names known to the system (used by the NLU to detect a channel
# named in the analyst's task).
KNOWN_CHANNELS = {ch for geo in GEO_STRUCTURE.values() for ch in geo["channels"]}
