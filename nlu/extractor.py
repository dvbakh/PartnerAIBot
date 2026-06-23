"""
Natural-language understanding (NLU).

Two functions:
  - extract_task(text)    — pull month / GEO list / channels / deadline from an
                            analyst's line
  - extract_budgets(text) — pull a list of {partner, budget} from a manager's line

Each first tries the LLM (when USE_LLM=True and a key is set) and, on error or
when the LLM is off, falls back to a deterministic rule-based parser. Thanks to
this the prototype works offline — important for the defense, when an external
API may be unavailable.

Note: the LLM prompts and the lookup dictionaries operate on Russian input, so
they are intentionally kept in Russian.
"""

import json
import logging
import re
from typing import Dict, List, Optional

from config import (USE_LLM, MISTRAL_API_KEY, LLM_BASE_URL, LLM_MODEL,
                    VALID_GEOS, KNOWN_CHANNELS)

logger = logging.getLogger(__name__)

# -------------------- dictionaries for the rule-based parser --------------------
# stems in various cases -> canonical form
_MONTH_ALIASES = {
    "январ": "январь", "феврал": "февраль", "март": "март", "апрел": "апрель",
    "ма": "май", "июн": "июнь", "июл": "июль", "август": "август",
    "сентябр": "сентябрь", "октябр": "октябрь", "ноябр": "ноябрь", "декабр": "декабрь",
}
_GEO_ALIASES = {
    "BY": "BY", "БЕЛАРУС": "BY", "БЕЛОРУС": "BY",
    "KZ": "KZ", "КАЗАХСТАН": "KZ", "КЗ": "KZ",
    "RU": "RU", "РОССИ": "RU", "РФ": "RU",
}
# channel aliases (uppercase) -> canonical channel name
_CHANNEL_ALIASES = {
    "MOBILE": "Mobile", "МОБАЙЛ": "Mobile", "МОБИЛ": "Mobile",
    "MEDIA": "Media", "МЕДИА": "Media",
    "AFFILIATE": "Affiliate", "АФФИЛИАТ": "Affiliate",
    "ПАРТНЁРСК": "Affiliate", "ПАРТНЕРСК": "Affiliate",
}


# ============================================================
# LLM client (created lazily, only when actually needed)
# ============================================================
def _llm_client():
    from openai import OpenAI
    return OpenAI(api_key=MISTRAL_API_KEY, base_url=LLM_BASE_URL)


def _llm_json(system_prompt: str, user_message: str) -> Optional[object]:
    """Call the LLM forcing a JSON reply. Returns None on error."""
    try:
        client = _llm_client()
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception:
        logger.exception("LLM request failed, falling back to rules")
        return None


# ============================================================
# Analyst task
# ============================================================
def extract_task(text: str) -> Dict:
    """Returns {'month', 'geo_list', 'channels', 'deadline'}.

    'channels' may be empty — that means "all channels of the chosen GEOs".
    """
    if USE_LLM:
        # LLM system prompt kept in Russian (operates on Russian input)
        system = (
            "Ты извлекаешь параметры задачи из сообщения аналитика. "
            "Верни только JSON с полями: month (строка-месяц или null), "
            "geo_list (массив кодов из BY, KZ, RU), "
            "channels (массив из Mobile, Media, Affiliate; пустой, если канал не указан), "
            "deadline (строка или null)."
        )
        data = _llm_json(system, text)
        if isinstance(data, dict):
            return _normalize_task(data)
    return _rule_extract_task(text)


def _normalize_task(data: Dict) -> Dict:
    geos = data.get("geo_list") or []
    geos = [g.upper() for g in geos if str(g).upper() in VALID_GEOS] \
        if isinstance(geos, list) else []
    chans = data.get("channels") or []
    chans = [c for c in chans if c in KNOWN_CHANNELS] if isinstance(chans, list) else []
    return {
        "month": data.get("month"),
        "geo_list": geos,
        "channels": chans,
        "deadline": data.get("deadline"),
    }


def _rule_extract_task(text: str) -> Dict:
    low = text.lower()
    upper = text.upper()

    # month
    month = None
    for stem, full in _MONTH_ALIASES.items():
        if stem in low:
            month = full
            break

    # geo
    geos = []
    for alias, code in _GEO_ALIASES.items():
        if alias in upper and code not in geos and code in VALID_GEOS:
            geos.append(code)

    # channels (optional)
    channels = []
    for alias, canonical in _CHANNEL_ALIASES.items():
        if alias in upper and canonical not in channels and canonical in KNOWN_CHANNELS:
            channels.append(canonical)

    # deadline: a date like dd.mm(.yyyy) or a phrase after "до"/"дедлайн"
    deadline = None
    m = re.search(r"\b\d{1,2}[.\-/]\d{1,2}(?:[.\-/]\d{2,4})?\b", text)
    if m:
        deadline = m.group(0)
    else:
        m = re.search(r"(?:дедлайн|до)\s+([^\n,.;]+)", low)
        if m:
            deadline = m.group(1).strip()

    return {"month": month, "geo_list": geos, "channels": channels, "deadline": deadline}


# ============================================================
# Manager budgets
# ============================================================
def extract_budgets(text: str) -> List[Dict]:
    """Returns a list of {'partner': str, 'budget': float}."""
    if USE_LLM:
        # LLM system prompt kept in Russian (operates on Russian input)
        system = (
            "Ты извлекаешь из сообщения список партнёров и их бюджетов. "
            'Верни только JSON-массив объектов с полями "partner" (строка) '
            'и "budget" (число). Никаких пояснений.'
        )
        data = _llm_json(system, text)
        records = _coerce_budget_list(data)
        if records:
            return records
    return _rule_extract_budgets(text)


def _coerce_budget_list(data) -> List[Dict]:
    """Coerce various LLM reply shapes into a list of {partner, budget}."""
    if data is None:
        return []
    if isinstance(data, dict):
        for key in ("budgets", "items", "data", "result"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            if "partner" in data:
                data = [data]
            else:
                return []
    out = []
    for item in data if isinstance(data, list) else []:
        try:
            out.append({"partner": str(item["partner"]).strip(),
                        "budget": float(item["budget"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _rule_extract_budgets(text: str) -> List[Dict]:
    """
    Rule-based parser. Understands lines such as:
        Google 1000
        Meta - 2 500
        Яндекс: 3000
        TikTok — 12 000.50
    """
    records: List[Dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.search(r"([\d][\d \u00A0]*(?:[.,]\d+)?)\s*$", line)
        if not m:
            continue
        num_raw = m.group(1).replace("\u00A0", "").replace(" ", "").replace(",", ".")
        try:
            budget = float(num_raw)
        except ValueError:
            continue
        partner = line[: m.start()].strip(" \t-:—–=•·")
        if not partner:
            continue
        records.append({"partner": partner, "budget": budget})
    return records
