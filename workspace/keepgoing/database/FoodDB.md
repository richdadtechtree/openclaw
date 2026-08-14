# FoodDB Schema & Quick Reference

SQLite Database: `~/pt_data/pt.db` (Table: `diet`)

## Schema
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `date` (TEXT, YYYY-MM-DD)
- `meal` (TEXT, 아침/점심/저녁/간식)
- `items` (TEXT)
- `protein_g` (REAL)
- `raw` (TEXT)
- `created_at` (TEXT)

## 주요 조회 쿼리
- 당일 식단 목록: `SELECT * FROM diet WHERE date = DATE('now', 'localtime');`
- 일별 총 단백질량: `SELECT date, SUM(protein_g) FROM diet GROUP BY date ORDER BY date DESC;`
