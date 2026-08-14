# 🗺️ OpenClaw 시스템 전체 맵 (실제 서버 기준)

> 작성일: 2026-08-13 | 서버 파일 직접 분석 기반

---

## 1. 전체 구조 한눈에 보기

```
[사용자: 이형준(형준 님)]
        │
        ├── Slack ──────────────────────────────────────────────┐
        │   ├── @그레이트리 (뚜떵또) → 신문분석 / 노션저장 / 구글연동
        │   ├── @GYM종국 (김종국)  → PT코치 / 운동기록 / DB저장
        │   └── @책읽남            → 노션 독서기록 → 책 한문장 브리핑
        │
        └── Telegram ───────────────────────────────────────────┐
            ├── default 봇 (비활성)  → 뉴스브리핑 (현재 OFF)
            └── pt 봇 (비활성)       → PT 트레이너 (현재 OFF)
```

---

## 2. 에이전트 목록 (openclaw.json 기준)

| ID | 이름 | 채널 | 워크스페이스 | 상태 |
|----|------|------|-------------|------|
| `main` | 뚜떵또 (그레이트리) | Slack default/ddupro | `/workspace` | ✅ 활성 |
| `keepgoing` | GYM종국 (김종국) | Slack keepgoing | `/workspace/keepgoing` | ✅ 활성 |
| `bookman` | 책읽남 | Slack bookman | `/workspace/bookman` | ✅ 활성 |
| `pt-trainer` | PT 트레이너 | Telegram pt봇 | `/agents/pt-trainer` | ⚠️ 텔레그램 비활성 |
| `ddu` | ddu | - | `/workspace/ddu` | 🔵 설정됨 |

---

## 3. Slack 봇 상세

### 3-1. 🤖 그레이트리 팀장 (뚜떵또) — `main` 에이전트

**Slack 계정**: `default` + `ddupro` (둘 다 활성)
**역할**: 신문 분석가 / 총괄 관리자
**인물**: 뚜떵또 — 영리하고 유머러스한 데이터 분석가 AI 🧐✨
**사용자**: 이형준 (형준 님)

**주요 기능**:
| 기능 | 트리거 | 동작 |
|------|--------|------|
| 신문 브리핑 | "신문 브리핑", "뉴스 브리핑" | news_fetcher.py → 분석 → 구글시트 저장 |
| 노션 링크 저장 | 링크 + 키워드 전송 | notion_save_url.py 실행 |
| 구글 캘린더/Gmail | "오늘 일정", "안읽은 메일" | gog CLI 실행 |
| 웹 검색 | 일반 질문 | Brave Search API |

**슬랙 채널 (requireMention: false)**:
- `C0BMLB1RXMG`, `C0BMHERHA77`, `C0BNK1VGVNZ`
- `C0BNB0YRGSY`, `C0BMJENDF62`(주식대시보드), `C0BMN9FN073`(keepgoing)

**바인딩**:
```json
{ "agentId": "main", "match": { "channel": "slack" } }
```
→ Slack의 모든 DM/채널(keepgoing 제외)에 응답

---

### 3-2. 💪 김종국 (GYM종국) — `keepgoing` 에이전트

**Slack 계정**: `keepgoing` (활성)
**채널**: `C0BMN9FN073`에만 바인딩
**역할**: 개인 PT 코치
**인물**: 김종국 — GYM종국, 30년 경력 헬스 전도사

**성격/말투**:
- 반말 사용, 친한 형이 후배에게 하듯
- 문장 끝에 "ㅎ", "ㅎㅎ" 자주 사용
- 직설적이고 팩폭, 사랑이 담긴 엄격함
- "맛있다", "딸기맛?" 같은 독특한 운동 표현

**코칭 범위**:
- 운동 (근력 중심, 40분 루틴)
- 식단 ("단백질 먹었어?")
- 수면 (최소 6시간 체크)
- 스트레스 관리

**특별 규칙**:
- 🍺 음주 → 다음날 유산소 30분 추가 벌칙
- 야식 → 다음날 하체 운동 필수
- 3일 연속 미보고 → "살아있긴 해?"

**데이터 저장** (핵심):
```bash
/home/ubuntu/pt_system/venv/bin/python \
  /home/ubuntu/pt_system/scripts/save_message.py "형준이 원문"
```
→ 저장 결과를 웹대시보드 `http://mystatus-btr.duckdns.org` 에 반영

**바인딩**:
```json
{
  "agentId": "keepgoing",
  "match": { "channel": "slack", "peer": { "kind": "channel", "id": "C0BMN9FN073" } }
}
```

---

### 3-3. 📚 책읽남 — `bookman` 에이전트

**Slack 계정**: `bookman` (활성)
**역할**: 노션 독서기록에서 책 한 문장 브리핑
**인물**: 책읽남 — 부드럽고 정확하게

**동작 방식**:
1. `get_notion_book.py` 실행
2. 노션 DB(`678f2c0b-d124-4889-8571-b019ec30f971`)에서 책 조회
3. 순서대로 (중복 배제) 한 문장 선택
4. 브리핑 전송

**브리핑 형식**:
```
"좋은 글 한문장"
<문장 한 줄>
<책 제목> 저자
```

**문장 선택 우선순위**:
1. 노션 `한 문장` 프로퍼티
2. `깨달은 점` 프로퍼티
3. 본문 블록에서 10자 이상 텍스트 추출
4. 없으면 기본 문구

**상태 추적**: `book_sequence_state.json` (마지막 인덱스 저장)

**⚠️ 문제**: `get_notion_book.py`에 Notion API 토큰 하드코딩 → git 제외됨

---

## 4. Telegram 봇 (현재 비활성)

| 계정 | 봇 | 상태 | 역할 |
|------|-----|------|------|
| `default` | 뚜떵또 텔레그램 | `enabled: false` | 뉴스 브리핑 |
| `pt` | PT 트레이너 | `enabled: false` | PT 기록/코칭 |

> 텔레그램은 현재 전부 비활성. Slack으로 이전됨.

---

## 5. Cron 스케줄 (jobs.json.migrated 기준)

| 잡 이름 | 에이전트 | 시각 (KST) | 활성 | 내용 |
|---------|----------|-----------|------|------|
| Daily Weather Report | main | 매일 06:00 | ✅ ON | 강릉 날씨 + 옷차림 추천 → 텔레그램 |
| pt-daily-report | pt-trainer | 매일 19:30 | ✅ ON | PT 일일 리포트 → 텔레그램 |
| pt-weekly-report | pt-trainer | 일요일 20:00 | ✅ ON | PT 주간 리포트 → 텔레그램 |
| morning-briefing | main | 매일 07:00 | ❌ OFF | 뉴스 브리핑 → 텔레그램 |
| morning-news-briefing | main | 매일 07:30 | ❌ OFF | 뉴스 브리핑 → 텔레그램 |
| evening-briefing | main | 매일 18:00 | ❌ OFF | 뉴스 브리핑 → 텔레그램 |
| evening-news-briefing | main | 매일 19:30 | ❌ OFF | 뉴스 브리핑 → 텔레그램 |

> ⚠️ **중요**: 텔레그램 봇이 `enabled: false`이므로, ON 상태인 cron 잡(날씨/PT)도 **실제로는 전송 안 됨**

---

## 6. Stock 프로젝트 (별도 - `~/stock/stock`)

| 기능 | 시각 | 채널 | 상태 |
|------|------|------|------|
| 주식 대시보드 → 슬랙 | 평일 15:40 | Slack `C0BMJENDF62` | ✅ |
| 관심종목 급등락 알림 | ~10분 주기 | 텔레그램 + 슬랙 | ✅ |
| 사이드카 감지 알림 | 장중 발동 시 | 슬랙 | ✅ |

openclaw와 별개 프로세스 (`nohup venv/bin/python scheduler.py`)

---

## 7. 데이터 흐름

```
[뉴스 브리핑 (온디맨드)]
  사용자 "신문 브리핑" →
  news_fetcher.py → news_data.json →
  AI 분석 → briefing_sheet.md →
  sheets_push.py → 구글 시트
                → 사용자에게 전송

[책읽남 브리핑]
  트리거(수동/cron) →
  get_notion_book.py →
  노션 DB 조회 → 랜덤 한 문장 →
  슬랙 전송

[김종국 PT 기록]
  형준 메시지 →
  save_message.py 자동 실행 →
  ~/pt_system/ DB 저장 →
  mystatus-btr.duckdns.org 반영 →
  코칭 답변 전송

[노션 링크 저장]
  슬랙에 링크 전송 (키워드 포함) →
  notion_save_url.py 실행 →
  노션 해당 표에 저장
```

---

## 8. ⚠️ 현재 안 되는 것 / 문제 목록

### 🔴 긴급
| 문제 | 원인 | 해결 |
|------|------|------|
| 뉴스 브리핑 자동 스케줄 없음 | `cron/jobs.json` 없음 (jobs.json.migrated만 존재) | jobs.json 생성 필요 |
| 텔레그램 전체 비활성 | `enabled: false` | 필요 시 재활성화 |
| 날씨/PT cron ON이지만 전송 안 됨 | 텔레그램 비활성이 원인 | 텔레그램 활성 or 슬랙으로 전환 |

### 🟡 주의
| 문제 | 원인 | 해결 |
|------|------|------|
| 책읽남 자동 발송 없음 | Heartbeat 비어있음, cron 미등록 | cron 또는 heartbeat에 스케줄 추가 |
| `get_notion_book.py` 토큰 하드코딩 | git 보안 정책 위반 | `.env`로 분리 |
| Gemini API 설정 오류 | `api: openai-completions` → 잘못된 값 | `google-generative-ai`로 변경 필요 |
| stock scheduler 재부팅 시 종료 | systemd 미등록 | systemd user 유닛 등록 |
| yfinance 미국 지수 차단 | 서버 IP 차단 | KIS 대체 |

### 🟢 정상 동작
- 슬랙 그레이트리(뚜떵또) 대화 ✅
- 슬랙 김종국 PT 코치 대화 ✅
- 슬랙 책읽남 (수동 요청 시) ✅
- 주식 슬랙 대시보드 (15:40) ✅
- 관심종목 급등락 슬랙/텔레그램 알림 ✅
- 노션 링크 저장 ✅

---

## 9. 주요 파일 위치 (서버 기준)

```
~/.openclaw/
├── openclaw.json          ← 메인 설정 (에이전트/봇/채널/모델)
├── .env                   ← API 키 모음 (gitignored)
├── cron/
│   └── jobs.json          ← ⚠️ 없음! jobs.json.migrated 참고
├── workspace/             ← 그레이트리 워크스페이스
│   ├── SOUL.md            ← 뉴스분석가 규칙
│   ├── news_fetcher.py    ← RSS 수집
│   ├── get_notion_book.py ← 책읽남 노션 조회
│   ├── sheets_push.py     ← 구글시트 저장
│   ├── bookman/           ← 책읽남 워크스페이스
│   └── keepgoing/         ← 김종국 워크스페이스
│       ├── SOUL.md        ← 김종국 역할/말투 규칙
│       └── IDENTITY.md    ← GYM종국 정체성
├── agents/
│   └── pt-trainer/        ← PT 트레이너 (텔레그램 전용)
└── scripts/
    ├── notion_save_url.py ← 노션 링크 저장
    ├── slack_briefing.py  ← 주식 슬랙 발송
    └── stock_alert_slack.py ← 관심종목 슬랙 알림

~/stock/stock/             ← 주식 프로젝트 (별도)
~/pt_system/               ← PT DB 및 리포트 스크립트
    ├── scripts/save_message.py   ← 기록 저장
    └── reports/daily_report.py  ← 일일 리포트
```

---

## 10. 수정하면 바로 반영되는 파일들 (git → 서버 자동 동기화)

| 파일 | 용도 | 수정하면? |
|------|------|----------|
| `workspace/SOUL.md` | 뚜떵또 분석 규칙 | 즉시 반영 |
| `workspace/keepgoing/SOUL.md` | 김종국 말투/규칙 | 즉시 반영 |
| `workspace/bookman/SOUL.md` | 책읽남 브리핑 규칙 | 즉시 반영 |
| `workspace/news_fetcher.py` | RSS 수집 로직 | 즉시 반영 |
| `workspace/sheets_push.py` | 구글시트 저장 | 즉시 반영 |
| `scripts/*.py` | 유틸리티 스크립트 | 즉시 반영 |

> **단**: `openclaw.json`, `.env`는 gitignored → 서버에서 직접 수정

---

## 11. 지금 당장 해야 할 것

1. **`cron/jobs.json` 복원** → 뉴스 브리핑 자동화 재개
2. **책읽남 cron 추가** → 매일 아침 책 한 문장 자동 발송
3. **Gemini API 설정 수정** → `openai-completions` → `google-generative-ai`
4. **`get_notion_book.py` 토큰 환경변수화** → `.env`로 이동
5. **텔레그램 필요 여부 결정** → 슬랙으로 완전 이전할지 여부
