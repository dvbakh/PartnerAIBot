"""SQLite initialisation, reset and demo-history seeding."""

import sqlite3
from pathlib import Path

DB_PATH = Path("partner_ai.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            geo_list TEXT NOT NULL,
            channels TEXT NOT NULL DEFAULT '[]',
            deadline TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # A collector serves one (GEO, channel) subtask for one manager.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS collectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            geo TEXT NOT NULL,
            channel TEXT NOT NULL,
            manager_name TEXT,
            manager_chat_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS budget_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            geo TEXT NOT NULL,
            channel TEXT NOT NULL,
            manager_name TEXT,
            partner TEXT NOT NULL,
            budget REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    """)

    # Last month's budgets — the baseline the validator compares against.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budget_history (
            geo TEXT NOT NULL,
            channel TEXT NOT NULL,
            partner TEXT NOT NULL,
            budget REAL NOT NULL,
            PRIMARY KEY (geo, channel, partner)
        )
    """)

    conn.commit()
    conn.close()


def reset_db(seed_history: bool = True) -> None:
    """Clear data before a repeat demonstration."""
    conn = get_connection()
    cur = conn.cursor()
    for table in ("budget_records", "collectors", "tasks", "budget_history"):
        cur.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    if seed_history:
        seed_demo_history()


def seed_demo_history() -> None:
    """
    Fill in last month's history so the validator has something to compare to.
    Values are chosen to make an anomaly easy to trigger in the demo:
    e.g. sending 'Meta 9000' for BY/Mobile while last month it was 2400.
    """
    rows = [
        ("BY", "Mobile", "Google", 1000.0),
        ("BY", "Mobile", "Meta", 2400.0),
        ("BY", "Media", "Yandex", 3000.0),
        ("KZ", "Mobile", "Google", 1200.0),
        ("KZ", "Affiliate", "Admitad", 800.0),
    ]
    conn = get_connection()
    cur = conn.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO budget_history (geo, channel, partner, budget) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
