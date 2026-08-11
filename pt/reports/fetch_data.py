from datetime import date, timedelta
from pathlib import Path
import sys
sys.path.append(str(Path("/home/ubuntu/pt_system")))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.db import get_conn
def fetch_range(days=1):
    end = date.today()
    start = end - timedelta(days=days - 1)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM workouts WHERE record_date BETWEEN ? AND ? ORDER BY record_date, id",
        (start.isoformat(), end.isoformat()),
    )
    workouts = cur.fetchall()
    cur.execute(
        "SELECT * FROM meals WHERE record_date BETWEEN ? AND ? ORDER BY record_date, id",
        (start.isoformat(), end.isoformat()),
    )
    meals = cur.fetchall()
    cur.execute(
        "SELECT * FROM vitals WHERE record_date BETWEEN ? AND ? ORDER BY record_date, id",
        (start.isoformat(), end.isoformat()),
    )
    vitals = cur.fetchall()
    conn.close()
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "workouts": [dict(row) for row in workouts],
        "meals": [dict(row) for row in meals],
        "vitals": [dict(row) for row in vitals],
}
