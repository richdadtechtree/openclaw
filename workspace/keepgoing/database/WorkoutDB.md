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

## ✍️ 기록 저장(쓰기) — 사용자가 운동을 말하면 반드시 실행
직접 INSERT 하지 말고 저장기 스크립트를 쓴다(웹 대시보드와 동일 DB 에 안전 저장):
```bash
python3 ~/.openclaw/scripts/save_message.py --json '{"workouts":[{"exercise":"스쿼트","sets":5,"reps":8,"weight_kg":100}]}'
```
자세한 규칙은 `../AGENTS.md` 의 "🚨 기록 저장" 참고. 모르는 값(무게 등)은 생략.
