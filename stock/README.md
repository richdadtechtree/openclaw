# stock/ — 주식 프로젝트 소스 (vendored)

이 폴더는 서버 `~/stock/stock` 에서 실행되는 **주식 대시보드/알림 프로젝트의 소스(.py)**를
openclaw repo 로 가져온(vendored) 것입니다. 목적: **claude.ai(Anthropic)에서 직접 편집 →
git push → 서버 자동 반영**. (별도 레포 `richdadtechtree/stock` 이 push 불가라 우회.)

## 동작 흐름
```
claude.ai 에서 stock/*.py 편집
      │  git push (main)
      ▼
서버 cron: git-auto-pull.sh  ── 새 커밋 감지 → repo 동기화
      │
      ▼
scripts/sync-stock.sh  ── stock/*.py 를 ~/stock/stock 로 rsync (코드만)
      │                     · 변경 있을 때만 scheduler 단일 인스턴스 재시작
      ▼
~/stock/stock  ── 실제 실행(venv/DB/.env/스크린샷은 그대로 보존)
```

## 무엇이 여기 들어오나 / 안 들어오나
- ✅ 추적: `*.py` 소스 (scheduler.py, market_data.py, trigger_engine.py, notifier.py, capture.py, app.py 등)
- ❌ 비추적(서버 전용): `venv/`, `*.sqlite*`(trigger_state 등), `.env`(비밀),
  `monitored_stocks.json`(감시종목 데이터 — 앱/서버에서 수정), 스크린샷/로그
  → `.gitignore` 에서 제외됨. **감시종목은 서버가 authoritative** (repo 가 덮어쓰지 않음).

## 최초 씨딩 (서버에서 1회, 현재 서버 코드 기준)
> 서버 `~/stock/stock` 가 GitHub `richdadtechtree/stock` 보다 최신이므로 **서버 파일을 기준**으로 가져온다.
```bash
cd ~/.openclaw
mkdir -p stock
# 코드(.py)만 반입. venv/DB/.env/json/미디어 제외.
rsync -rcm --include='*/' --include='*.py' --exclude='*' ~/stock/stock/ ~/.openclaw/stock/
#   (rsync 필요. 없으면: sudo apt-get install -y rsync)
git add stock/
git status            # stock/*.py 만 스테이징됐는지 확인 (비밀/DB 없어야 함!)
git commit -m "vendor: stock 소스 반입 (서버 현재 코드)"
git push origin main  # 서버에서 push 가능해야 함. 안 되면 아래 참고.
```
push 후 claude.ai 에서 `git pull` 하면 그때부터 여기서 편집·동기화 가능.

### 서버에서 push 가 안 될 때(권한 없음)
- `ls -1 ~/stock/stock/*.py` 목록을 claude.ai 에 붙여주고, 파일 내용을 옮겨 담아 커밋하는 방식으로 대체.
- 또는 `richdadtechtree/stock` 읽기 권한이 있으면 그 소스를 기준선으로 받고 서버와의 차이만 반영.

## 주의
- **커밋 전 `git status` 로 비밀/DB 가 안 섞였는지 반드시 확인.** (`.env`, `*.sqlite`, `openclaw.json` 등)
- 실행 폴더 `~/stock/stock` 는 nohup 실행이라 재부팅 시 꺼짐 → systemd user 유닛 상시화 권장(별도 작업).
