# TOOLS.md — pt-trainer 로컬 설정

이 에이전트는 `~/pt_system`의 파이썬 스크립트를 `exec` 툴로 호출해
기록을 SQLite DB에 저장하고 리포트를 만든다. (신문 분석가(`main`)가
`news_fetcher.py`를 exec로 호출하는 것과 같은 패턴이다.)

## 경로

- pt_system 루트: `/home/ubuntu/pt_system`
- 파이썬(가상환경): `/home/ubuntu/pt_system/venv/bin/python`  ← 반드시 이걸로 실행
- SQLite DB: 스크립트가 `.env`의 `DATABASE_PATH`(기본 `/home/ubuntu/pt_system/pt_data.db`)를 읽는다

## 기록 저장 (운동·식단·체중·수면·컨디션 입력 시)

```
/home/ubuntu/pt_system/venv/bin/python /home/ubuntu/pt_system/scripts/save_message.py "<사용자 원문>"
```

- 출력 예:
  ```
  [기록 완료]
  - 운동: 1개
  - 식단: 1개
  - 바이탈: 저장됨
  ```
- 파싱 규칙: 체중=`체중 72kg`, 수면=`수면 7시간`, 컨디션=`컨디션 보통`,
  운동/식단은 키워드 + 횟수(회)/세트(세트) 인식. 인식 안 돼도 `raw_messages`에는 항상 남는다.

## 리포트

- 일일: `/home/ubuntu/pt_system/venv/bin/python /home/ubuntu/pt_system/reports/daily_report.py`
- 주간: `/home/ubuntu/pt_system/venv/bin/python /home/ubuntu/pt_system/reports/weekly_report.py`
- 두 스크립트 모두 리포트 전문을 stdout으로 출력하고 `reports` 테이블에도 저장한다.

## 주의

- 스크립트는 어느 경로에서 실행해도 되지만, **가상환경 파이썬**을 써야
  의존성(`google-genai`, `python-dotenv`)이 로드된다. 시스템 python으로 실행하면 실패한다.
- 웹 대시보드(`pt-dashboard.service`)와 리포트가 이 스크립트들이 쓴 같은 DB를 읽는다.
- 기존 독립 봇 `telegram_polling.py`(`pt-telegram.service`)는 이 에이전트로 대체되므로
  **중복 실행하지 않는다.** (같은 `pt` 봇 토큰을 둘이 폴링하면 충돌한다.)
