from storage.db import get_connection


class CollectorRepository:

    @staticmethod
    def create(
        task_id: int,
        geo: str,
        channel: str,
        respondent_chat_id: int,
        status: str = "created"
    ) -> int:

        conn = get_connection()

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO collectors
            (
                task_id,
                geo,
                channel,
                respondent_chat_id,
                status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                task_id,
                geo,
                channel,
                respondent_chat_id,
                status
            )
        )

        conn.commit()

        collector_id = cur.lastrowid

        conn.close()

        return collector_id

    @staticmethod
    def get_by_task(task_id: int):

        conn = get_connection()

        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM collectors
            WHERE task_id = ?
            """,
            (task_id,)
        )

        rows = cur.fetchall()

        conn.close()

        return rows

    @staticmethod
    def update_status(
        collector_id: int,
        status: str
    ):

        conn = get_connection()

        cur = conn.cursor()

        cur.execute(
            """
            UPDATE collectors
            SET status = ?
            WHERE id = ?
            """,
            (
                status,
                collector_id
            )
        )

        conn.commit()

        conn.close()

    @staticmethod
    def get_active_by_chat_id(chat_id: int):
        conn = get_connection()

        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM collectors
            WHERE respondent_chat_id = ?
            AND status = 'waiting_response'
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id,)
        )

        row = cur.fetchone()

        conn.close()

        return row