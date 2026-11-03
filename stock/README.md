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

## 시장 지수 페이지의 시세 출처와 관심종목 팝업

- 코스피·코스닥·S&P 500·나스닥: 네이버 금융 우선, 한국투자증권(KIS)·Yahoo Finance 순으로 대체.
  KIS 대체 경로의 S&P 500·나스닥은 각각 SPY·QQQ ETF 가격을 배율로 환산한 값으로, 실제 지수와 차이가 날 수 있다.
- QLD·TQQQ: 네이버 시간외 시세가 있으면 우선 사용. 그 외에는 KIS 가격을 네이버와 교차검증하며, 실패하면 네이버·Yahoo로 대체.
- 비트코인: 원화 업비트 → 빗썸, 달러 바이낸스 → 코인베이스.
- 원/달러: 네이버 → 두나무 → ECB(Frankfurter). 긴 기간 그래프는 별도 역사 자료를 사용한다.
- 화면 카드의 출처가 실제 선택된 제공처다. 제공처 응답이 지연될 수 있고, 페이지의 갱신 시각은 거래소 체결 시각이 아니다.

### 관리자 공용 관심종목
- /market 에서만 표시한다. 승인된 관리자 또는 IP 비밀번호 관리자가 종목을 추가·삭제한다.
  일반 회원은 목록·시세·팝업을 볼 수 있고, 직접 API를 호출해도 변경할 수 없다.
- 국내 6자리 코드 또는 미국 티커와 이름을 입력한다(최대 20종목). 확인 가능한 시세가 있어야 저장한다.
- 별도 market_watch.sqlite 에 저장한다(기본 ~/.openclaw/secret/gate/, MARKET_WATCH_DB로 변경).
  기존 monitored_stocks.json과 발송용 감시목록은 수정하지 않는다.
- 관심종목 가격은 기존 수집 함수 사용: 국내 KIS → Yahoo, 미국 Yahoo → KIS.
- 팝업 기준: 전일 종가 대비 +2%, +4%, +6%… . 한 번에 여러 구간을 넘으면 최고 구간과 도달 범위를 한 팝업으로 표시.
  하락 뒤 같은 구간을 다시 넘어도 반복하지 않는다. 처음 접속했을 때 이미 구간 이상인 경우에도 한 번 표시한다.
- 브라우저가 보이는 동안 20초마다 확인하며 서버 시세 캐시는 60초다. 가격 확인 실패·180초 이상 된 캐시는 알리지 않는다.
  브라우저/계정/종목/시장 현지 날짜(국내 서울, 미국 뉴욕)별로 최고 알림 구간을 기억한다.
  이 날짜는 서버 확인일이며 제공처의 체결 날짜를 보장하지 않는다. 새 날짜에 휴장·지연 시세를 다시 확인할 수도 있다.
- 브라우저 저장소를 삭제하거나 다른 브라우저로 열면 이미 넘은 구간이 다시 표시될 수 있다.
  페이지를 닫았을 때의 시스템 푸시·메신저 발송은 하지 않는다.
- 검증: python -m unittest discover -s scripts -p test_market_watch.py -v,
  node scripts/test_market_watch.js (Playwright Chromium 필요). GitHub Actions: Market watch checks.
