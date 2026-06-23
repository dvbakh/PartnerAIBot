"""
Reporter agent.

When the coordinator signals that the data is collected (REQUEST), the reporter
aggregates the budgets for the task, builds a summary for the analyst and
exports the result. In demo mode (USE_SHEETS=False) it writes a CSV and sends
the summary to the chat; with Google Sheets enabled it appends rows there.

The summary shows: totals by channel, totals by GEO, and how many partners each
manager submitted. The exported table has the columns:
    month (mm-dd-yyyy), GEO, Detailed (Channel), Partner, Budget

User-facing strings are kept in Russian.
"""

import csv
import logging
from collections import defaultdict
from datetime import datetime
from typing import List

from agents.base import BaseAgent
from config import GEO_STRUCTURE, USE_SHEETS
from core.messages import AgentMessage, Performative
from storage.repositories import BudgetRepository, HistoryRepository, TaskRepository

logger = logging.getLogger(__name__)

# Russian month name -> month number
_RU_MONTH_NUM = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}


def _month_to_date(month_name: str) -> str:
    """Render a Russian month name as the first day of that month, mm-dd-yyyy.

    The task carries no year, so the current year is used.
    """
    num = _RU_MONTH_NUM.get((month_name or "").strip().lower())
    year = datetime.now().year
    if not num:
        return month_name or ""
    return f"{num:02d}-01-{year}"


class ReporterAgent(BaseAgent):
    def __init__(self, bus, notify):
        super().__init__("reporter", bus, notify)

    async def receive(self, message: AgentMessage) -> None:
        if message.performative != Performative.REQUEST:
            return
        task_id = message.content["task_id"]
        analyst_chat_id = message.content.get("analyst_chat_id")
        await self._build_report(task_id, analyst_chat_id)

    async def _build_report(self, task_id: int, analyst_chat_id: int) -> None:
        rows = BudgetRepository.get_by_task(task_id)
        task = TaskRepository.get(task_id)

        if not rows:
            await self.notify_user(analyst_chat_id,
                                   "Данные собраны, но бюджетов не поступило.")
            TaskRepository.update_status(task_id, "done")
            return

        month_str = _month_to_date(task.month if task else "")
        csv_path = self._write_csv(task_id, month_str, rows)
        if USE_SHEETS:
            self._export_to_sheets(month_str, rows)

        # store collected values as history for next month's checks
        for r in rows:
            HistoryRepository.upsert(r["geo"], r["channel"], r["partner"], r["budget"])

        summary = self._format_summary(task, rows, csv_path)
        await self.notify_user(analyst_chat_id, summary)
        TaskRepository.update_status(task_id, "done")

        await self.send(AgentMessage(
            performative=Performative.CONFIRM,
            sender=self.name, receiver="coordinator",
            content={"task_id": task_id}, conversation_id=task_id,
        ))

    @staticmethod
    def _write_csv(task_id: int, month_str: str, rows: List) -> str:
        path = f"report_task_{task_id}.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["month", "GEO", "Detailed (Channel)", "Partner", "Budget"])
            for r in rows:
                writer.writerow([month_str, r["geo"], r["channel"],
                                 r["partner"], r["budget"]])
        return path

    @staticmethod
    def _format_summary(task, rows: List, csv_path: str) -> str:
        by_channel = defaultdict(float)
        by_geo = defaultdict(float)
        partners_by_manager = defaultdict(int)
        total = 0.0
        for r in rows:
            by_channel[r["channel"]] += r["budget"]
            by_geo[r["geo"]] += r["budget"]
            partners_by_manager[r["manager_name"] or "—"] += 1
            total += r["budget"]

        lines = [f"📊 Отчёт по задаче за {task.month if task else ''}:", ""]
        lines.append("Суммы по каналам:")
        for ch, amount in by_channel.items():
            lines.append(f"  {ch}: {amount:.0f}")
        lines.append("Суммы по GEO:")
        for geo, amount in by_geo.items():
            lines.append(f"  {geo}: {amount:.0f}")
        lines.append("Партнёров прислал каждый менеджер:")
        for mgr, cnt in partners_by_manager.items():
            lines.append(f"  {mgr}: {cnt}")
        lines.append("")
        lines.append(f"Итого: {total:.0f} по {len(rows)} партнёрам.")
        lines.append(f"Файл: {csv_path}")
        return "\n".join(lines)

    @staticmethod
    def _export_to_sheets(month_str: str, rows: List) -> None:
        """Export to Google Sheets (only if enabled)."""
        try:
            from utils.sheets import append_budget_rows
            by_geo_channel = defaultdict(list)
            for r in rows:
                by_geo_channel[(r["geo"], r["channel"])].append(r)
            for (geo, channel), items in by_geo_channel.items():
                sheet_id = GEO_STRUCTURE.get(geo, {}).get("google_sheet_id")
                if not sheet_id:
                    continue
                payload = [{"month": month_str, "geo": geo, "channel": channel,
                            "partner": x["partner"], "budget": x["budget"]}
                           for x in items]
                append_budget_rows(sheet_id, channel, payload)
        except Exception:
            logger.exception("Failed to export to Google Sheets")
