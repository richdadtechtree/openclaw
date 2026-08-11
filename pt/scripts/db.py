import sqlite3
from pathlib import Path

from scripts.config import DATABASE_PATH

DB_PATH = Path(DATABASE_PATH)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 👈 누락되었던 핵심 코드입니다!
    return conn