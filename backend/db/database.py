# backend/db/database.py

import sqlite3
from config.settings import DATABASE_PATH
from db.models import CREATE_STORIES_TABLE


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(CREATE_STORIES_TABLE)
        conn.commit()
