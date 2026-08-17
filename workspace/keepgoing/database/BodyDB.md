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

## ✍️ 기록 저장(쓰기) — 사용자가 체중/수면/컨디션/음주를 말하면 반드시 실행
직접 INSERT 하지 말고 저장기 스크립트를 쓴다. `vitals` 는 날짜당 1행이라 같은 날은 덮어쓰기(upsert)된다:
```bash
python3 ~/.openclaw/scripts/save_message.py --json '{"vitals":{"weight_kg":78,"sleep_hours":7,"condition":"good","alcohol":0}}'
```
`condition` 은 excellent/good/fair/tired/poor 중 하나. 자세한 규칙은 `../AGENTS.md` 의 "🚨 기록 저장" 참고.
