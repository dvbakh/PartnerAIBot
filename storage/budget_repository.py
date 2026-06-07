from storage.db import get_connection


class BudgetRepository:

    @staticmethod
    def create(
        task_id: int,
        geo: str,
        channel: str,
        partner: str,
        budget: float
    ):

        conn = get_connection()

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO budget_records
            (
                task_id,
                geo,
                channel,
                partner,
                budget
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                task_id,
                geo,
                channel,
                partner,
                budget
            )
        )

        conn.commit()

        conn.close()