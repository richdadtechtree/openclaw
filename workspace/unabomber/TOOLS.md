# TOOLS.md — 유나바머 로컬 노트

부동산 분석에 필요한 환경별 정보를 여기에 적는다.

## 앱웹 데이터 소스
- 앱웹 URL: https://richdadtechtree.duckdns.org/
- 수집 스크립트: `~/.openclaw/workspace/unabomber_fetch.py`
  - 1차: `python3 ~/.openclaw/workspace/unabomber_fetch.py` (requests, 가벼움)
  - SPA 폴백: `~/stock/stock/venv/bin/python ~/.openclaw/workspace/unabomber_fetch.py` (Playwright)
  - 결과: `~/.openclaw/workspace/unabomber_data.json` (`api`/`page_text`/`fetched_at`)
- 환경변수: `UNABOMBER_URL`(주소 override), `UNABOMBER_NO_PW=1`(Playwright 끔)
- 인증: 현재 공개 가정. 로그인 필요하면 스크립트에 세션/헤더 추가 필요(추후 보완).
- 실제 필드 매핑(가격·거래량·전세·매물·공급·금리·심리 등)은 첫 실행 후 확정 → SOUL.md 반영.

## 실행 메모
- 서버에 맨 `python` 없음 → `python3` 또는 stock venv 사용.
- 데이터 기준 시점(`fetched_at`)을 항상 브리핑에 포함.
- ⚠️ 이 수집기는 개발 샌드박스에선 사이트 egress 차단으로 검증 불가 →
  **서버에서 1회 실행해 unabomber_data.json 생성/키 구조를 확인**해야 완성.

## 전송 채널
- Slack: 그레이트리 팀장 계정의 **새 채널**(채널 ID `[[TODO]]`)에 바인딩.
