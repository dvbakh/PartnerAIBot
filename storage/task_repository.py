import json

from models.task import Task
from storage.db import get_connection


class TaskRepository:

    @staticmethod
    def create(task: Task) -> int:

        conn = get_connection()

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO tasks
            (
                month,
                geo_list,
                deadline,
                status
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                task.month,
                json.dumps(task.geo_list),
                task.deadline,
                task.status
            )
        )

        conn.commit()

        task_id = cur.lastrowid

        conn.close()

        return task_id

    @staticmethod
    def get(task_id: int):

        conn = get_connection()

        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM tasks
            WHERE id = ?
            """,
            (task_id,)
        )

        row = cur.fetchone()

        conn.close()

        if not row:
            return None

        return Task(
            id=row["id"],
            month=row["month"],
            geo_list=json.loads(row["geo_list"]),
            deadline=row["deadline"],
            status=row["status"]
        )

    @staticmethod
    def update_status(
        task_id: int,
        status: str
    ):

        conn = get_connection()

        cur = conn.cursor()

        cur.execute(
            """
            UPDATE tasks
            SET status = ?
            WHERE id = ?
            """,
            (
                status,
                task_id
            )
        )

        conn.commit()

        conn.close()