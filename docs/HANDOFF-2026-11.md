# 인수인계서 (2026-11-02 작성)

> **범위**: 2026-10-28 까지 만든 것 전부. **2026-10-29 이후의 최근 작업은 인계 대상이 아니다**(맨 아래 '인계 제외' 목록 — 손대지 말 것).
> 자세한 이력·명령은 `CLAUDE.md`(규칙·함정·스크립트 표)와 `HANDOFF.md`(날짜별 기록)에 있다. 이 문서는 그 둘을 **처음 맡는 사람 눈높이**로 묶은 요약이다.

---

## 0. 처음 맡으면 이 순서로 읽기
1. `CLAUDE.md` — **응답 규칙**(답마다 '쉽게 정리' 섹션, 사용자가 할 일은 1→2→3 + 복붙 명령)과 **함정** 목록.
2. 이 문서 1~5장.
3. 손댈 기능의 `CLAUDE.md` 표 줄 + 해당 검사 스크립트(`scripts/test_*`).

---

## 1. 시스템 지도

| 무엇 | 어디 | 어떻게 돎 |
|---|---|---|
| 리포 | `richdadtechtree/openclaw` (**main 에 push = 서버 반영**) | 서버 cron 1분마다 `scripts/git-auto-pull.sh` → pull + `openclaw daemon restart` + `scripts/sync-stock.sh` |
| openclaw(AI 에이전트 '뚜떵또') | 서버 `/home/ubuntu/.openclaw` | systemd user `openclaw-gateway` · 게이트웨이 `127.0.0.1:18789` |
| stock(주가·웹 서버) | 서버 `/home/ubuntu/stock/stock` (소스는 리포 `stock/`) | `scheduler.py`(nohup, **프로세스 2개가 정상** = 스케줄러 + uvicorn 8000). `sync-stock.sh` 가 `.py` 만 rsync 후 재시작 |
| PT 대시보드 | `scripts/pt_dashboard.py` (Flask 5001) | `https://mystatus-btr.duckdns.org/pt/` |
| 공개 주소 | `https://mystatus-btr.duckdns.org` | nginx `/etc/nginx/sites-enabled/pt-dashboard` 가 `/economy·/dig·/ai·/gate·/privacy` 등을 8000 으로, 나머지는 5001 로 |
| 비밀 | `~/.openclaw/.env` (gitignore, stock `.env` 는 여기로 심볼릭 링크) | `openclaw.json` 은 **git 추적** — 서버에서 직접 고치면 1분 뒤 되돌아감 → 리포에서 고쳐 push |

**꼭 기억할 함정**
- 서버엔 맨 `python` 이 없다. 시스템 `python3` 엔 `requests` 없음 → stock 은 `~/stock/stock/venv/bin/python`.
- `richdadtechtree/stock` 리포는 push 불가(403). stock 코드는 **이 리포의 `stock/`** 에서 고친다.
- 대시보드 화면은 `stock/templates/index.html` 과 `stock/index.html` **둘 다** 똑같이 고칠 것(앞엣것이 실제로 쓰임).
- 개발 환경(클로드)에서는 매경·한경·네이버·Threads·구글/카카오 로그인 서버가 **막혀 있다** → 가짜 서버로 검사하고, 실제 확인은 서버 명령으로.

---

## 2. 인계하는 기능 (상태 · 핵심 파일 · 서버 점검)

### A. openclaw 에이전트 (슬랙·텔레그램)
| 기능 | 상태 | 파일 | 점검 |
|---|---|---|---|
| 뚜떵또 온디맨드 신문 브리핑 → 구글 시트/노션 저장 | 운영 중 | `workspace/SOUL.md`, `workspace/news_fetcher.py`, `scripts/sheets_push.py`, `notion_push.py` | 슬랙에서 "신문 브리핑 해줘" |
| 종국이(GYM종국) 데일리 21:00·주간 일 20:00 | 운영 중(중복 발송 수정됨) | `scripts/pt_briefing.py` | `python3 scripts/test_pt_briefing_dedupe.py` |
| 종국이 보고 독촉 톡(10:00·13:30·18:30·20:30) | 운영 중 | `scripts/pt_nudge.py`, `setup-briefing-cron.sh` | `python3 scripts/test_pt_nudge.py` · 끄기 `.env PT_NUDGE=off` |
| PT 대시보드 `/pt` (구글 로그인) | 운영 중 | `scripts/pt_dashboard.py` | 브라우저로 `/pt/` |
| 책읽남 글귀(노션 실제 문장만, AI 미경유) | 운영 중 | `scripts/get_notion_book.py`, `book_slack.py` | `--check`, `--dry-run` |
| 메르 블로그 새 글 → 슬랙(요약 3~5줄 + 한줄평) | 운영 중 | `scripts/mer_blog_slack.py`, `setup-mer-cron.sh` | `python3 scripts/test_mer_blog_slack.py` · 서버 `--show URL` |
| AI 토론 `#ai-토론` | **부분**(Gemini 만 확인, Qwen·Mistral 키·모델 ID 미설정) | `scripts/debate.py`, `workspace/debate/` | `python3 scripts/debate.py "상태"` |

### B. stock (주가)
| 기능 | 상태 | 파일 |
|---|---|---|
| 평일 15:40 대시보드 캡처 → 슬랙 | 운영 중 | `scripts/slack_briefing.py` (openclaw cron `stock-slack-briefing`) |
| 관심종목 급등락 알림(슬랙, 국장=장중만·미장=24h) | 운영 중 | `stock/scheduler.py alert_job`, `scripts/stock_alert_slack.py` |
| 대시보드 카드 8장(지수 4·QLD·TQQQ·₿·💱), 기간 6개월~10년, 기준 가로선 | 운영 중 | `stock/charts.py`, `index_history.py`, `crypto_data.py`, `fx_data.py` · 검사 `node scripts/test_dashboard_btc.js` |

### C. 신문 원본 파이프라인
| 단계 | 파일 | 비고 |
|---|---|---|
| 수집기 패치(오늘치 로컬 보존, 제목 `신문스크랩` 필터, 05:00~07:00 재시도) | `scripts/patch-newspaper-*.sh`, `set-newspaper-schedule.sh` | 수집기 본체는 `~/newspaper` (이 리포 밖) |
| 원본 → 웹 캐시(로컬 링크 우선, 없으면 구글 드라이브) 30분마다 | `scripts/news_sync.py`, `setup-news-cron.sh` | 종료코드 0/2/1 |
| 지면 글자 읽기(tesseract) → 요약 기사와 지면 자동 연결 | `scripts/news_page_text.py` | 서버에 `tesseract-ocr-kor` 필요 |
| 보관 기간(사진 14일 등) | `scripts/retention_cleanup.py --status` | 깨진 링크 경고 |
| 요약은 **사용자의 ChatGPT 슬랙 앱**이 만든다 | `docs/chatgpt-newspaper-instructions.md`, `docs/chatgpt-newspaper-prompt.md` | 형식 규칙은 GPT 지침 쪽에 넣어야 함 |

### D. 신문 요약 웹 `/economy` (예전 `/slack`)
- 화면 `stock/slack_digest_live.html`, 데이터 `stock/app.py`(`/economy/data`, `/api/news/*`).
- 요약 글 해석(제목·WHAT/WHY/HOW·표·목록·연결 5가지), 기사 옆 지면 사진, 사진 뷰어(확대·✋이동·형광펜·PDF 저장·옆 요약 칸), 글자 크기, 화이트/다크, 매일경제 사설 칸, AI 오디오 브리핑.
- ⚠️ GPT 가 형식을 자주 바꾼다 → 해석은 **낱말보다 모양(구조)으로** 판단하게 짜여 있다. 새 형식이 오면 `scripts/test_viewer_table.js`·`test_viewer_list.js` 에 실제 메시지를 넣고 고친다.

### E. 경제 공부(디그) `/dig`
- 매경 '디그' 뉴스레터를 Gmail(IMAP, 읽기 전용)로 받아 화면에 보여 줌. `stock/dig_mail.py`·`dig_view.html`·`dig_pdf.py`, cron `scripts/setup-dig-cron.sh`.
- `.env`: `DIG_GMAIL_USER`·`DIG_GMAIL_APP_PASSWORD`(Gmail 앱 비밀번호). 검사 `python3 scripts/test_dig_mail.py`.

### F. AI 소식 `/ai` (기본 수집까지)
- Threads @choi.openai·GeekNews 새 글 모으기. `stock/ai_news.py`·`ai_view.html`. 서버 점검 `cd ~/stock/stock && venv/bin/python ai_news.py threads`.
- (댓글 수집 고도화는 최근 작업 → 인계 제외)

### G. 로그인·동의·승인 게이트 (10-23~10-28 분)
- `stock/gate.py` + `docs/gate-setup.md`. 구글·카카오 로그인 → 개인정보 동의(닉네임 직접 입력) → 입장. 최소 수집(소셜 고유번호+닉네임).
- 관리자 화면 `/gate/admin`(승인·차단·이용 기한), 서버 IP 접속은 `.env GATE_IP_ADMIN_PASSWORD` 로만, 화면 모드 계정 저장, 처리방침 `/privacy`.
- 관리자 지정은 서버에서만: `python3 stock/gate.py admin 회원번호`. 비상 해제 `.env GATE_ENABLED=0`.
- 검사 `python3 scripts/test_gate.py` (fastapi·httpx 필요).

---

## 3. 남은 일 (인계받는 사람이 할 것, 우선순위 순)
1. **노출된 키 재발급** — 텔레그램 봇 2개·Slack·Brave·Gateway·Gemini 가 대화 기록에 노출됨. 재발급 후 `~/.openclaw/.env` 교체.
2. **stock 스케줄러 상시화** — 지금 nohup 이라 서버 재부팅 시 꺼진다(15:40 캡처·알림 중단). systemd user 유닛(`stock-scheduler`)으로 바꾸기 권장.
3. **AI 토론 마무리** — `OPENROUTER_API_KEY`·`MISTRAL_API_KEY` 발급, 무료 모델 ID 확정(`DEBATE_QWEN_MODEL` 등), GPT 게이트웨이 경로 실호출 확인, 빈 멘션 때 질문을 지어내는 버그(SOUL.md 규칙 추가).
4. **`HANDOFF.md` 의 오래된 '진행 중' 항목 상태 확인** — A(Gemini 백업 모델), B(텔레그램 15:30 지수 브리핑 끄기). 적용됐는지 서버에서 확인 후 문서 정리.
5. **오래된 화면 검사 스크립트 고치기** — `scripts/test_viewer_*.js` 대부분이 옛 주소 `/slack/data` 를 흉내 내서 지금 화면(`/economy/data`)에선 시작하자마자 멈춘다. 가짜 서버에 `/economy`·`/economy/data` 를 더하면 됨(`test_viewer_terms.js` 가 본보기). `test_viewer_editorial.js` ③ 1항목도 실패 중.
6. **yfinance 차단 영향 줄이기**(선택) — 서버 IP 에서 야후가 막혀 미국 지수 ATH 로딩이 느림. 네이버·KIS 쪽으로 의존 줄이기.
7. **잔여 정리**(선택) — 원격 `seed-stock` 브랜치 삭제, 텔레그램 발송 코드 정리(지금은 키가 없으면 조용히 건너뜀).

## 4. 아직 서버에서 확인 못 한 것 (개발 환경이 막혀서 가짜로만 검사)
| 무엇 | 서버에서 확인하는 명령 |
|---|---|
| 매일경제 사설 실제 HTML | `cd ~/stock/stock && venv/bin/python mk_editorial.py --probe` |
| 환율 소스(네이버·두나무·ECB) | `cd ~/stock/stock && venv/bin/python fx_data.py --probe` |
| 메르 블로그 한줄평 뽑기 | `python3 ~/.openclaw/scripts/mer_blog_slack.py --show <글주소>` |
| 디그 메일 사진이 든 PDF | 웹 `/dig` 에서 ⤓ PDF |
| 지면 글자 읽기(tesseract) | `python3 ~/.openclaw/scripts/news_page_text.py --show` |

## 5. 작업 방식 (지금까지의 약속)
- 개발 브랜치에서 작업 → 검사 통과 → 커밋·push → 사용자가 **"머지해줘"** 하면 PR 만들고 바로 merge(main 반영 = 서버 반영).
- 커밋 메시지는 한국어, 무엇을 왜 바꿨는지. 고친 기능은 `CLAUDE.md` 표 해당 줄에 날짜·사용자 요청·검사 항목 수를 함께 적는다.
- **지어내지 않기**가 공통 원칙: 못 찾으면 빈칸/안내(사설·제목·한줄평·글귀 모두 같음).
- 사용자 답변 규칙: 맨 끝 '쉽게 정리'(🎯·🔎·🛠·✅), 사용자가 할 일은 1→2→3 한 단계에 명령 하나 + 성공 모습.

---

## 6. 인계 제외 — 최근 작업 (2026-10-29 이후, 손대지 말 것)
지금 사용자와 계속 다듬는 중이라 넘기지 않는다. 고칠 일이 생기면 먼저 확인받을 것.
- 로그인: 다시 접속할 때 '로그인하지 못했어요' 화면 제거(10-29), **자동 로그인**(구글·카카오 `prompt=none`, 11-01)
- 화면 맨 위 메뉴 고정(10-29)
- **🔥 찰스 챌린지 전체**(`/challenge`, 기수·글쓰기·뷰어·용어장·전용 입구, 10-30~)
- **AI 소식 Threads 댓글 수집 고도화**(이어진 글·댓글에 단 답·점검 `debug`, 남의 댓글 내용 저장 안 함, 10-30~31)
- **한국경제 사설 추가** + 챌린지 '오늘의 사설'(11-01)
- **📖 관리자 용어 노트**(신문 요약 화면 오른쪽 아래, IP 관리자 공유, 11-01~02)
- **📈 시장 지수 `/market` 탭**(11-02)
