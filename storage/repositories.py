"""Repositories — a thin access layer over the SQLite tables."""

import json
from typing import List, Optional

from models.task import Task
from storage.db import get_connection


class TaskRepository:
    @staticmethod
    def create(task: Task) -> int:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tasks (month, geo_list, channels, deadline, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (task.month, json.dumps(task.geo_list, ensure_ascii=False),
             json.dumps(task.channels, ensure_ascii=False),
             task.deadline, task.status),
        )
        conn.commit()
        task_id = cur.lastrowid
        conn.close()
        return task_id

    @staticmethod
    def get(task_id: int) -> Optional[Task]:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return Task(
            id=row["id"],
            month=row["month"],
            geo_list=json.loads(row["geo_list"]),
            channels=json.loads(row["channels"]) if row["channels"] else [],
            deadline=row["deadline"],
            status=row["status"],
        )

    @staticmethod
    def update_status(task_id: int, status: str) -> None:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()
        conn.close()


class CollectorRepository:
    @staticmethod
    def create(task_id: int, geo: str, channel: str, manager_name: str,
               manager_chat_id: int, status: str = "created") -> int:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO collectors
               (task_id, geo, channel, manager_name, manager_chat_id, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, geo, channel, manager_name, manager_chat_id, status),
        )
        conn.commit()
        collector_id = cur.lastrowid
        conn.close()
        return collector_id

    @staticmethod
    def get(collector_id: int):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM collectors WHERE id = ?", (collector_id,))
        row = cur.fetchone()
        conn.close()
        return row

    @staticmethod
    def get_by_task(task_id: int) -> List:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM collectors WHERE task_id = ? ORDER BY id", (task_id,))
        rows = cur.fetchall()
        conn.close()
        return rows

    @staticmethod
    def update_status(collector_id: int, status: str) -> None:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE collectors SET status = ? WHERE id = ?",
                    (status, collector_id))
        conn.commit()
        conn.close()

    @staticmethod
    def get_active_by_chat_id(chat_id: int):
        """The oldest collector still waiting for an answer from this manager."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM collectors
               WHERE manager_chat_id = ? AND status = 'waiting_response'
               ORDER BY id ASC LIMIT 1""",
            (chat_id,),
        )
        row = cur.fetchone()
        conn.close()
        return row

    @staticmethod
    def get_waiting_for_chat(chat_id: int) -> List:
        """All collectors currently waiting for an answer from this manager."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM collectors
               WHERE manager_chat_id = ? AND status = 'waiting_response'
               ORDER BY id ASC""",
            (chat_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    @staticmethod
    def get_unanswered_by_task(task_id: int) -> List:
        """Collectors that were asked but did not deliver (timed out / failed)."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM collectors
               WHERE task_id = ? AND status IN ('timed_out', 'failed')
               ORDER BY id ASC""",
            (task_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    @staticmethod
    def list_waiting_for_chat(chat_id: int) -> List:
        """All collectors currently waiting for an answer from this manager
        (used to build the per-manager buttons in demo mode)."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM collectors
               WHERE manager_chat_id = ? AND status = 'waiting_response'
               ORDER BY id ASC""",
            (chat_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows


class BudgetRepository:
    @staticmethod
    def create(task_id: int, geo: str, channel: str, manager_name: str,
               partner: str, budget: float) -> None:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO budget_records
               (task_id, geo, channel, manager_name, partner, budget)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, geo, channel, manager_name, partner, budget),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_by_task(task_id: int) -> List:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM budget_records WHERE task_id = ? ORDER BY id",
                    (task_id,))
        rows = cur.fetchall()
        conn.close()
        return rows


class HistoryRepository:
    """Last month's budgets — the basis for anomaly checks."""

    @staticmethod
    def get(geo: str, channel: str, partner: str):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT budget FROM budget_history WHERE geo=? AND channel=? AND partner=?",
            (geo, channel, partner),
        )
        row = cur.fetchone()
        conn.close()
        return row["budget"] if row else None

    @staticmethod
    def upsert(geo: str, channel: str, partner: str, budget: float) -> None:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO budget_history (geo, channel, partner, budget) "
            "VALUES (?, ?, ?, ?)",
            (geo, channel, partner, budget),
        )
        conn.commit()
        conn.close()


def count_waiting_for_chat(chat_id: int) -> int:
    """How many subtasks currently await this manager's answer (load measure)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS c FROM collectors "
        "WHERE manager_chat_id=? AND status='waiting_response'",
        (chat_id,),
    )
    c = cur.fetchone()["c"]
    conn.close()
    return c
