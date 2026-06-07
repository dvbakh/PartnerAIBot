import sqlite3
from pathlib import Path

DB_PATH = Path("partner_ai.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()

    cur = conn.cursor()

    # ==========================
    # Задачи
    # ==========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        month TEXT NOT NULL,

        geo_list TEXT NOT NULL,

        deadline TEXT NOT NULL,

        status TEXT NOT NULL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ==========================
    # Агенты-сборщики
    # ==========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS collectors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        task_id INTEGER NOT NULL,

        geo TEXT NOT NULL,

        channel TEXT NOT NULL,

        respondent_chat_id INTEGER NOT NULL,

        status TEXT NOT NULL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(task_id)
            REFERENCES tasks(id)
    )
    """)

    # ==========================
    # Собранные бюджеты
    # ==========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS budget_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        task_id INTEGER NOT NULL,

        geo TEXT NOT NULL,

        channel TEXT NOT NULL,

        partner TEXT NOT NULL,

        budget REAL NOT NULL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(task_id)
            REFERENCES tasks(id)
    )
    """)

    conn.commit()
    conn.close()