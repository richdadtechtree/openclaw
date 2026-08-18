# FoodDB Schema & Quick Reference

SQLite Database: `~/pt_data/pt.db` (Table: `diet`)

## Schema
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `date` (TEXT, YYYY-MM-DD)
- `meal` (TEXT, 아침/점심/저녁/간식/물)
- `items` (TEXT)
- `protein_g` (REAL)
- `raw` (TEXT)
- `created_at` (TEXT)

## 주요 조회 쿼리
- 당일 식단 목록: `SELECT * FROM diet WHERE date = DATE('now', 'localtime');`
- 일별 총 단백질량: `SELECT date, SUM(protein_g) FROM diet GROUP BY date ORDER BY date DESC;`

## ✍️ 기록 저장(쓰기) — 사용자가 먹은 것을 말하면 반드시 실행
직접 INSERT 하지 말고 저장기 스크립트를 쓴다(웹 대시보드와 동일 DB 에 안전 저장):
```bash
python3 ~/.openclaw/scripts/save_message.py --json '{"diet":[{"meal":"점심","items":"닭가슴살 200g, 현미밥","protein_g":46}]}'
```
자세한 규칙은 `../AGENTS.md` 의 "🚨 기록 저장" 참고. `protein_g` 등 모르는 값은 생략.

⚠️ **물/수분 섭취는 항상 `meal:"물"` 로 저장한다.** "수분"·"워터" 등 다른 표현을 쓰지 말 것 —
검색·집계가 갈라진다(과거에 실제로 이 문제가 있었음). 저장기(`save_message.py`)가 "수분" 등이
들어와도 자동으로 "물"로 정규화하긴 하지만, 애초에 `meal:"물"` 로 넣는 게 안전하다.
