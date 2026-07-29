# pt-trainer ↔ pt_system 연동 가이드

PT 트레이너 에이전트가 텔레그램 대화/사진에서 운동·식단·바이탈을 뽑아
`~/pt_system`의 파이썬 스크립트로 **SQLite DB에 실제 저장**하고,
매일/매주 리포트를 자동 발송하도록 연결한다.
(신문 분석가 `main`이 `news_fetcher.py`를 exec로 부르는 것과 동일한 패턴.)

## 이 브랜치에서 바뀐 것

| 파일 | 내용 |
|---|---|
| `agents/pt-trainer/AGENTS.md` | 기본 템플릿 → PT 기록 워크플로(입력 시 `save_message.py` exec 저장, `/daily`·`/weekly`, 이미지 처리, 역할 경계) |
| `agents/pt-trainer/TOOLS.md` | pt_system 경로·가상환경 파이썬·스크립트 호출법 등록 |
| `cron/jobs.json` | `pt-trainer`용 cron 2개 추가 — 일일 21:00, 주간 일요일 20:00(Asia/Seoul) |

## 전제 (서버에서 한 번 확인)

- pt_system 위치: `/home/ubuntu/pt_system`, 가상환경: `/home/ubuntu/pt_system/venv`
- `.env`에 `DATABASE_PATH`, `GEMINI_API_KEY`, `GEMINI_MODEL` 설정돼 있어야 리포트가 동작
- 경로가 다르면 `AGENTS.md`/`TOOLS.md`/`cron/jobs.json`의 절대경로를 실제 값으로 수정

## 서버 반영 절차

```bash
# 1) 이 레포를 서버에서 최신화 (또는 아래 3개 파일만 ~/.openclaw로 복사)
cd ~/.openclaw
git fetch origin claude/newspaper-briefing-openclo-fzhmn7
git checkout claude/newspaper-briefing-openclo-fzhmn7   # 백업 레포를 그대로 쓰는 경우

# 2) 기록 저장이 실제로 되는지 수동 검증
/home/ubuntu/pt_system/venv/bin/python \
  /home/ubuntu/pt_system/scripts/save_message.py "운동 푸쉬업 20개 3세트, 체중 72kg"
# → [기록 완료] 출력 + pt_data.db 에 행이 쌓이면 성공

# 3) 게이트웨이 재시작 (cron/에이전트 설정 리로드)
openclaw gateway restart
openclaw gateway status

# 4) 기존 독립 봇 은퇴 (같은 pt 봇 토큰 중복 폴링 방지)
sudo systemctl disable --now pt-telegram.service
#   대시보드는 유지: pt-dashboard.service 는 그대로 둔다
```

## 검증 체크리스트

- [ ] `pt` 봇에 "저녁 계란후라이, 쌀밥" 전송 → 코칭 답변 + DB `meals`/`raw_messages`에 저장됨
- [ ] "운동 푸쉬업 20개 3세트" 전송 → `workouts`에 저장됨
- [ ] `/daily` 전송 → 일일 리포트 수신
- [ ] 웹 대시보드에 위 기록이 보임
- [ ] 21:00 / 일요일 20:00 자동 리포트 수신
- [ ] `pt-telegram.service` 중지 후에도 `pt` 봇이 정상 응답(=오픈클로가 담당)

## ⚠️ 보안 (선행 권장)

이 레포(`richdadtechtree/openclaw`)는 현재 **public** 이며
`openclaw.json*`에 봇 토큰·게이트웨이 토큰·API 키가, `sessions/`에 개인 건강 대화가 커밋돼 있다.

1. 레포를 **private** 로 전환
2. 텔레그램 봇 토큰(BotFather `/revoke`), Brave/Google API 키, 게이트웨이 토큰 **재발급**
3. `.gitignore`에 `openclaw.json*`, `*.sqlite*`, `agents/**/sessions/`, `memory/`, `media/` 추가 후
   git 히스토리에서 제거(`git filter-repo` 등)
