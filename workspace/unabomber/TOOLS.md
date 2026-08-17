# TOOLS.md — 유나바머 로컬 노트

부동산 분석에 필요한 환경별 정보를 여기에 적는다.

## 앱웹 데이터 소스 (검증 완료 2026-08-17)
- 앱웹 URL: https://richdadtechtree.duckdns.org/ — "부동산 연구소" (KB부동산·국토교통부).
  **Plotly Dash 앱** → requests 로는 데이터 못 받음, Playwright 렌더로 수집.
- 수집: `python3 ~/.openclaw/workspace/unabomber_fetch.py`
  (openclaw python3 에 playwright 설치돼 있어 이 한 줄로 렌더까지 됨. 실패 시 `~/stock/stock/venv/bin/python` 로 대체)
  - 결과: `~/.openclaw/workspace/unabomber_data.json`
    · `page_text` = 렌더된 실제 숫자(1차 근거)
    · `api` = Dash `_dash-update-component` 등(차트 원값)
    · `fetched_at` = 기준 시각
- 환경변수: `UNABOMBER_URL`(주소 override), `UNABOMBER_NO_PW=1`(Playwright 끔)
- 인증: 공개(`/admin/status` → admin:false, 로그인 불필요).
- 필드 매핑: SOUL.md 「필드 매핑」 참조. 기본 대시보드는 매매증감률/누적상승 TOP3 중심.

## 실행 메모
- 서버에 맨 `python` 없음 → `python3` 사용.
- 데이터 기준 시점(`fetched_at`)을 항상 브리핑에 포함.
- 없는 지표(거래량·전세·매물 등 다른 탭 데이터)는 창작 금지 → "데이터 없음".

## 전송 채널
- Slack: 그레이트리 팀장 계정의 **새 채널**(채널 ID `[[TODO]]`)에 바인딩.
