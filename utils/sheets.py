"""
Google Sheets export (optional).

Authorisation is performed LAZILY inside the functions, not at import time, so a
missing/invalid key file does not crash the whole bot at startup. Used only when
USE_SHEETS=True in config.

The exported table mirrors the CSV columns:
    month (mm-dd-yyyy), GEO, Detailed (Channel), Partner, Budget
"""

import logging
from typing import Dict, List

from config import GOOGLE_CREDS_FILE

logger = logging.getLogger(__name__)

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

_HEADER = ["month", "GEO", "Detailed (Channel)", "Partner", "Budget"]


def _client():
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_FILE, SCOPE)
    return gspread.authorize(creds)


def _get_or_create_worksheet(sheet, channel_name: str):
    import gspread
    try:
        ws = sheet.worksheet(channel_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=channel_name, rows="100", cols="5")
        ws.append_row(_HEADER)
    return ws


def append_budget_rows(sheet_id: str, channel: str, rows: List[Dict]) -> None:
    """Append budget rows to the channel worksheet of the given spreadsheet."""
    client = _client()
    sheet = client.open_by_key(sheet_id)
    ws = _get_or_create_worksheet(sheet, channel)
    for row in rows:
        ws.append_row([row.get("month", ""), row.get("geo", ""),
                       row.get("channel", channel),
                       row.get("partner", ""), row.get("budget", "")])
    logger.info("Sheets: appended %s rows to worksheet '%s'", len(rows), channel)
