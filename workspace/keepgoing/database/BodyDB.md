# BodyDB Schema & Quick Reference

SQLite Database: `~/pt_data/pt.db` (Table: `vitals`)

## Schema
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `date` (TEXT UNIQUE, YYYY-MM-DD)
- `weight_kg` (REAL)
- `sleep_hours` (REAL)
- `condition` (TEXT, excellent/good/fair/tired/poor)
- `alcohol` (INTEGER, 0 또는 1)
- `raw` (TEXT)
- `created_at` (TEXT)

## 주요 조회 쿼리
- 최근 체중 변화: `SELECT date, weight_kg FROM vitals WHERE weight_kg IS NOT NULL ORDER BY date DESC LIMIT 30;`
- 수면시간 & 음주 기록: `SELECT date, sleep_hours, alcohol FROM vitals ORDER BY date DESC LIMIT 7;`
