# WorkoutDB Schema & Quick Reference

SQLite Database: `~/pt_data/pt.db` (Table: `workouts`)

## Schema
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `date` (TEXT, YYYY-MM-DD)
- `exercise` (TEXT)
- `sets` (INTEGER)
- `reps` (INTEGER)
- `weight_kg` (REAL)
- `raw` (TEXT)
- `created_at` (TEXT)

## 주요 조회 쿼리
- 최근 운동 목록: `SELECT * FROM workouts ORDER BY date DESC, id DESC LIMIT 20;`
- 풀업 최고 기록(PR): `SELECT MAX(reps), date FROM workouts WHERE exercise LIKE '%풀업%';`
