# pt_system — 슬랙 기반 AI PT 트레이너 (DB + 웹 + 브리핑)

슬랙에 입력한 운동/식단/체중/수면/컨디션을 **DB(sqlite)** 에 저장하고,
그 데이터로 **웹 대시보드**(`mystatus-btr.duckdns.org`)와 **일간/주간 브리핑**을 제공한다.

- **표준 라이브러리만 사용**(sqlite3 + http.server). 서버에 pip 설치 불필요.
- 브리핑 집계는 **규칙 기반**(AI 미사용) → 모델 상태와 무관하게 항상 동작.
- 텔레그램은 폐기. 상호작용/기록/알림 모두 슬랙 기준.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `db.py` | 스키마(workouts/meals/vitals/ingest_log) + 조회 헬퍼. DB=`PT_DB_PATH` 또는 `pt_system/pt.sqlite` |
| `record.py` | 기록 CLI. **PT 에이전트가 `exec` 로 호출**해 슬랙 입력을 DB에 저장 |
| `briefing.py` | 일간/주간 브리핑 텍스트 생성(+`--slack` 전송) |
| `app.py` | 웹 대시보드(HTML) + `/api/*` JSON. DB 읽기 전용 |
| `pt-dashboard.service` | 대시보드 systemd --user 유닛 |

`pt.sqlite`(+`-wal`/`-shm`)는 `.gitignore` 대상 → **런타임 데이터는 서버에만** 존재.

---

## 배포 순서 (서버 `~/.openclaw`)

이 작업은 `claude/pt-trainer-telegram-slack-l68xn9` 브랜치에 있다. main 머지 후
자동 pull 로 반영되거나, 급하면 서버에서 직접 받는다:

```bash
cd ~/.openclaw
git fetch origin claude/pt-trainer-telegram-slack-l68xn9
git checkout origin/claude/pt-trainer-telegram-slack-l68xn9 -- pt_system agents/pt-trainer/TOOLS.md
```

### 1) DB 초기화 (최초 1회, 선택 — record 첫 호출 시 자동 생성됨)
```bash
python3 ~/.openclaw/pt_system/db.py
```

### 2) 슬랙 채널 지정 (.env)
```bash
# ~/.openclaw/.env 에 추가 (없으면 SLACK_BRIEFING_CHANNEL 로 폴백)
SLACK_PT_CHANNEL=C0XXXXXXX      # PT 대화/브리핑 채널
```

### 3) PT 에이전트를 슬랙에 연결 (openclaw.json — 서버 전용/비밀)
현재 `pt-trainer` 에이전트는 텔레그램 봇에 물려 있다. 슬랙에서 대화하려면
openclaw 슬랙 채널이 이 에이전트로 라우팅돼야 한다. **openclaw.json 은 gitignored** 이므로
서버에서 `jq` 로 직접 편집한다(백업 필수). 정확한 채널→에이전트 라우팅 키는
설치된 openclaw 버전 스키마에 따라 다르므로, 아래로 현재 구조를 먼저 확인:

```bash
cd ~/.openclaw
jq '.channels.slack' openclaw.json           # 슬랙 채널 설정 구조 확인
jq '.agents.list[] | {id,channels}' openclaw.json
openclaw config validate
```

> ⚠️ 라우팅 스키마 확인 전에는 `openclaw.json` 을 바꾸지 말 것. 구조를 붙여주면
> 정확한 jq 편집 커맨드를 만들어 준다. (텔레그램 봇 라우팅은 그대로 두고 슬랙만 추가/이전.)

### 4) 대시보드 상시 실행 (systemd)
```bash
mkdir -p ~/.config/systemd/user
cp ~/.openclaw/pt_system/pt-dashboard.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pt-dashboard
loginctl enable-linger $USER
systemctl --user status pt-dashboard
curl -s localhost:8770/healthz            # {"ok": true, ...}
```

### 5) nginx → mystatus-btr.duckdns.org
기존에 이 도메인을 다른 앱으로 서비스 중이라면 그 앱을 교체하거나 경로를 나눈다.
대시보드는 `127.0.0.1:8770` 에서 뜨므로 리버스 프록시만 연결하면 된다:

```nginx
# /etc/nginx/sites-available/mystatus  (예시)
server {
    listen 80;
    server_name mystatus-btr.duckdns.org;
    location / {
        proxy_pass http://127.0.0.1:8770;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```
```bash
sudo ln -sf /etc/nginx/sites-available/mystatus /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```
> 기존 대시보드 앱이 이미 이 포트/도메인을 쓰고 있으면 먼저 그 앱을 확인
> (`scripts/pt_inspect.py` 출력)한 뒤 교체 여부를 정한다.

### 6) 브리핑 자동화 (openclaw cron 또는 crontab)
일간(예: 21:00)·주간(일요일 20:00) 브리핑을 슬랙으로:
```bash
# crontab -e  (KST 서버 기준)
0 21 * * *  cd ~/.openclaw && /usr/bin/python3 pt_system/briefing.py daily  --slack
0 20 * * 0  cd ~/.openclaw && /usr/bin/python3 pt_system/briefing.py weekly --slack
```
openclaw cron(command job)으로 넣어도 된다. 채널은 `.env` 의 `SLACK_PT_CHANNEL`.

---

## 검증

```bash
cd ~/.openclaw
# 저장 테스트
python3 pt_system/record.py json '{"workouts":[{"type":"러닝","detail":"5km","duration_min":30}],"vitals":[{"weight_kg":72.4,"sleep_h":7}],"raw":"테스트"}'
# DB 확인
python3 -c "import sys;sys.path.insert(0,'pt_system');import db;c=db.connect(readonly=True);print(db.counts_for_date(c,db.today_str()))"
# 브리핑
python3 pt_system/briefing.py daily
# 대시보드
curl -s localhost:8770/api/summary | python3 -m json.tool | head
```

## 텔레그램 → 슬랙 전환 (기존 트래픽)

- **PT 대화**: 3)번으로 슬랙에 연결되면 자연히 슬랙에서 이루어진다.
- **기존 텔레그램 알림/브리핑(cron)**: `cron/jobs.json` 의 `delivery.channel` 이
  `telegram` 인 잡들을 슬랙으로 옮긴다. **정확한 슬랙 delivery 포맷은 openclaw 버전 스키마
  확인 후** 반영(현재 미변경 — 라이브 브리핑을 깨지 않기 위해).
- **과거 텔레그램 기록 백필(선택)**: `/.openclaw/telegram/` 에 남은 과거 대화에서
  운동/식단/체중을 뽑아 `record.py json` 으로 소급 저장할 수 있다. 폴더 포맷 확인
  (`scripts/pt_inspect.py`) 후 백필 스크립트를 만든다.
