import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import List, Dict

# Настройка доступа
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
CREDENTIALS_FILE = "GoogleCreds9cf91e5daeee.json"

credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
client = gspread.authorize(credentials)


def open_geo_sheet(sheet_id: str):
    """Открывает Google Таблицу по ID и возвращает объект sheet."""
    return client.open_by_key(sheet_id)


def get_or_create_channel_worksheet(sheet, channel_name: str):
    """
    Возвращает лист с названием канала (channel_name).
    Если листа нет — создаёт его с заголовками.
    """
    try:
        ws = sheet.worksheet(channel_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=channel_name, rows="100", cols="5")
        # Записываем заголовки
        ws.append_row(["Месяц", "Канал", "Партнер", "Сорс", "Бюджет"])
    return ws


def append_budget_rows(sheet_id: str, channel: str, rows: List[Dict[str, str]]):
    """
    Добавляет строки бюджета в лист канала внутри указанной таблицы.

    Параметры:
        sheet_id: ID Google Таблицы
        channel: название канала (например, "Mobile")
        rows: список словарей с ключами:
            - month (формат "01/05/2026")
            - partner (название партнёра)
            - source (источник/сорс)
            - budget (сумма)
    """
    sheet = open_geo_sheet(sheet_id)
    ws = get_or_create_channel_worksheet(sheet, channel)

    for row in rows:
        ws.append_row([
            row.get("month", ""),
            channel,
            row.get("partner", ""),
            row.get("source", ""),
            row.get("budget", "")
        ])
    print(f"[Sheets] Добавлено {len(rows)} строк в лист '{channel}' таблицы {sheet_id}")