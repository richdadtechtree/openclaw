# 로그인 잠금(구글·카카오) 켜는 법

`/slack`(신문 요약) · `/dig`(경제 공부)를 **구글 또는 카카오 로그인 + 개인정보 동의**를 마친 사람만 보게 합니다.
코드는 `stock/gate.py`. **설정이 덜 되어 있으면 잠금이 꺼진 채(열린 채) 유지**되므로, 코드를 먼저 반영해도 갑자기 못 들어가는 일은 없습니다.

잠그는 주소: `/slack`, `/slack/*`, `/dig`, `/dig/*`, `/api/dig/*`, `/api/news/*`  
그대로 두는 주소: 주가 대시보드 `/` 와 나머지 `/api/*`

> 왜 `http://158.179.162.52:8000` 으로는 로그인을 못 하나요?  
> 구글 로그인은 **도메인 + HTTPS** 주소만 받습니다(IP 주소·http 불가). 그래서 이미 HTTPS 가 되어 있는
> `https://mystatus-btr.duckdns.org` 에 두 화면을 함께 연결합니다.  
> 옛 주소(IP:8000)로 들어가도 **같은 잠금이 걸려 있어** 우회되지 않습니다(로그인이 끝나지 않을 뿐).

---

## 1. 서버 설정 값 (`~/.openclaw/.env`)

```bash
cat >> ~/.openclaw/.env <<'EOF'
GATE_BASE_URL=https://mystatus-btr.duckdns.org
GATE_APPROVAL=auto
PRIVACY_OPERATOR=여기에 이름(또는 운영자 별명)
PRIVACY_CONTACT=여기에 연락받을 이메일
GATE_GOOGLE_CLIENT_ID=(2번에서 받은 값)
GATE_GOOGLE_CLIENT_SECRET=(2번에서 받은 값)
GATE_KAKAO_REST_KEY=(3번에서 받은 값)
EOF
```

| 이름 | 뜻 |
|---|---|
| `GATE_BASE_URL` | 로그인에 쓰는 HTTPS 주소(끝에 `/` 없이) |
| `GATE_APPROVAL` | `auto` = 로그인+동의만 하면 입장(지금) / `manual` = 운영자 승인 필요(나중) |
| `PRIVACY_OPERATOR`, `PRIVACY_CONTACT` | 처리방침에 공개되는 **개인정보 보호책임자**. 법적으로 필수 — 비워 두면 처리방침에 빨간 안내가 보입니다 |
| `GATE_GOOGLE_*` / `GATE_KAKAO_*` | 아래 2·3번에서 발급. 둘 중 하나만 있어도 켜집니다 |
| `GATE_ENABLED=0` | 비상용: 잠금을 끕니다 |
| `PRIVACY_LOG_DAYS` | 처리방침에 적히는 접속 기록 보관일(기본 14) — 7번에서 실제 값과 맞추세요 |

설정이 맞는지 한 번에 점검(+ 등록할 주소를 그대로 알려 줌):

```bash
python3 ~/.openclaw/stock/gate.py check
```

## 2. 구글 로그인 키 만들기

1. https://console.cloud.google.com/apis/credentials → **사용자 인증 정보 만들기 → OAuth 클라이언트 ID → 웹 애플리케이션**
2. **승인된 리디렉션 URI**: `https://mystatus-btr.duckdns.org/gate/google/callback` (한 글자도 다르면 안 됨)
3. 나온 **클라이언트 ID / 보안 비밀번호**를 `.env` 의 `GATE_GOOGLE_CLIENT_ID` / `GATE_GOOGLE_CLIENT_SECRET` 에 넣기
4. **OAuth 동의 화면**: 사용자 유형 *외부*, 앱 이름·지원 이메일·개발자 연락처 입력,
   **개인정보처리방침 링크** = `https://mystatus-btr.duckdns.org/privacy`
5. 동의 화면 **게시 상태를 '프로덕션'으로**(테스트 상태면 등록한 테스트 사용자만 로그인됨)
- 요청하는 범위는 `openid profile` 뿐입니다(이메일 요청 안 함, 구글의 민감 범위 심사 불필요).
- 구글이 `duckdns.org` 같은 공유 도메인에 대해 경고를 띄우면 그 문구를 알려 주세요.

## 3. 카카오 로그인 키 만들기

1. https://developers.kakao.com → **내 애플리케이션 → 앱 만들기**
2. **앱 키 → REST API 키**를 `.env` 의 `GATE_KAKAO_REST_KEY` 에 넣기
3. **카카오 로그인 → 활성화 ON**, **Redirect URI** 에 `https://mystatus-btr.duckdns.org/gate/kakao/callback` 등록
4. **동의항목 → 닉네임(profile_nickname)** 설정. 이메일 등은 설정하지 않습니다(최소 수집).
5. (선택) **보안 → Client Secret 사용 ON** 으로 했다면 그 값을 `.env` 의 `GATE_KAKAO_CLIENT_SECRET` 에 추가

## 4. nginx 에 두 화면 연결 (이미 PT 대시보드가 쓰는 server 블록 안에)

PT 대시보드 설정 파일(보통 `/etc/nginx/sites-enabled/` 아래, `server_name mystatus-btr.duckdns.org;` 가 있는 파일)의
**HTTPS(443) server { } 안**에 아래 두 블록을 추가합니다. 기존 `location /` 는 그대로 둡니다.

```nginx
    # 신문 요약·경제 공부·로그인 화면 → stock 앱(8000)
    location ~ ^/(slack|dig|gate|privacy)(/|$) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 120s;      # PDF 처음 만들 때 몇 초 걸림
    }
    location ~ ^/api/(dig|news)/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 120s;
    }
```

```bash
sudo nginx -t && sudo systemctl reload nginx     # 문법 검사가 OK 일 때만 적용
```

PT 대시보드의 로그인 쿠키(`session`)와 겹치지 않도록 이쪽 쿠키 이름은 `gate_sess` 입니다.

## 5. 켜기 (stock 웹 서버 재시작)

`.env` 를 바꾸거나 `app.py` 가 바뀌면 stock 웹 서버를 다시 켜야 합니다. 켜질 때 로그에
`[gate] 잠금 켜짐 · 승인 방식=auto · 제공자=google,kakao` 가 찍히면 성공입니다.

확인: **시크릿(비공개) 창**에서 `https://mystatus-btr.duckdns.org/slack` → 로그인 화면이 나와야 합니다.

## 6. 나중에 '승인제'로 바꾸기

```bash
# .env 에서  GATE_APPROVAL=manual  로 바꾸고 stock 웹 서버 재시작
python3 ~/.openclaw/stock/gate.py pending        # 승인 대기 목록
python3 ~/.openclaw/stock/gate.py approve 12     # 12번 승인
python3 ~/.openclaw/stock/gate.py block 12       # 차단(이미 들어온 사람도 즉시)
python3 ~/.openclaw/stock/gate.py list           # 전체
python3 ~/.openclaw/stock/gate.py stats          # 상태별 인원
python3 ~/.openclaw/stock/gate.py delete 12      # 정보 삭제(요청 시)
```

- 전환 **이전**에 가입한 사람은 그대로 입장하고, **이후** 가입자부터 '승인 대기'가 됩니다.
- 승인 대기 화면은 사용자에게 "승인을 기다리고 있어요"로 보입니다.

## 7. 개인정보 관련 운영자 체크리스트 (코드가 대신해 줄 수 없는 것)

- [ ] `PRIVACY_OPERATOR`, `PRIVACY_CONTACT` 를 채웠다 (처리방침의 보호책임자 — 법 제31조)
- [ ] 접속 기록 보관 기간이 처리방침과 맞다: `cat /etc/logrotate.d/nginx` 에서 `daily`/`rotate 14` 인지 확인(다르면 `PRIVACY_LOG_DAYS` 수정)
- [ ] 서버가 해외 클라우드에 있다면(예: 오라클 클라우드 해외 리전) **국외 이전·처리 위탁 해당 여부**를 확인하고 처리방침 3항에 반영
- [ ] 이용자가 정보 열람·삭제를 요청하면 연락처(이메일)로 접수해 지체 없이 처리 — 삭제는 `gate.py delete 번호`
- [ ] 정보 유출이 의심되면 지체 없이 이용자에게 알리고 개인정보보호위원회(118)에 문의
- [ ] 처리방침·동의 문구를 고치면 `gate.py` 의 `POLICY_VERSION` 날짜를 바꾼다 → 모든 사용자가 다시 동의
- [ ] **공개 전 전문가(변호사·개인정보 전문가) 검토를 권장합니다.** 이 문서와 코드는 일반적인 법정 항목을 반영했지만 법률 자문이 아닙니다.

### ⚠️ 저작권 (개인정보보다 큰 위험일 수 있음)
신문 요약(매일경제 등)과 디그 뉴스레터 본문은 **원 저작자의 저작물**입니다. 불특정 다수에게 보여 주면(로그인을 걸어도)
공중송신으로 볼 수 있어 문제가 될 수 있습니다. 안전하게 하려면 ①`GATE_APPROVAL=manual` 로 **아는 사람만** 승인,
②본문 대신 **제목·핵심 요약·원문 링크 중심**으로 바꾸기, ③각 매체의 이용 허락 확인 중 하나 이상을 권합니다.
동의 화면에 "개인 학습용·재배포 금지" 확인 칸이 있지만 이것이 저작권 문제를 해결해 주지는 않습니다.

## 7-1. 로그인 유지 기간

한 번 로그인하고(승인제라면 승인까지 받으면) **계속 쓰는 동안은 다시 로그인하지 않습니다.**
로그인 쿠키는 1년 유효하고, 쓰는 동안 7일에 한 번 1년으로 다시 늘어납니다(1년 동안 한 번도 안 들어오면 만료).
- 승인 상태·동의 기록은 서버 DB 에 남아 있어 쿠키가 만료돼도 다시 로그인만 하면 그대로 입장합니다(처리방침이 바뀌지 않았다면).
- 차단·탈퇴한 사람은 쿠키가 남아 있어도 즉시 들어올 수 없고 연장도 되지 않습니다.
- 모두 강제로 로그아웃시키려면 `~/.openclaw/secret/gate/secret.key` 를 지우고 stock 서버를 재시작하세요.
- 처리방침에는 "마지막 이용 후 최대 1년"으로 안내되어 있습니다(`stock/gate.py` 의 `SESSION_DAYS` 를 바꾸면 처리방침 문구도 함께 고치고 `POLICY_VERSION` 을 올리세요).

## 8. 저장되는 정보 / 위치

`~/.openclaw/secret/gate/` (git 이 올리지 않는 폴더, 권한 700)
- `gate.sqlite` — 사용자(로그인 방식·고유번호·닉네임·상태·동의 시각), 동의 이력
- `secret.key` — 쿠키 서명 열쇠(지우면 모두 로그아웃)
- `internal.key` — 서버 내부 작업(PDF 만들기)용 열쇠

이메일·전화번호·프로필 사진은 **저장하지 않습니다.** 탈퇴(내 정보 화면)하면 사용자와 동의 이력이 즉시 삭제됩니다.

## 9. 문제 해결

| 증상 | 확인 |
|---|---|
| 로그인 화면이 안 나오고 그냥 열림 | `gate.py check` — 빠진 설정(`빠짐`)을 채우고 stock 서버 재시작 |
| 구글 `redirect_uri_mismatch` | 콘솔의 리디렉션 URI 가 `gate.py check` 가 알려 준 주소와 **정확히** 같은지 |
| 카카오 `KOE006` / 리디렉션 오류 | 카카오 앱의 Redirect URI 등록, 카카오 로그인 활성화 |
| 로그인했는데 계속 로그인 화면 | 브라우저 쿠키 차단 여부, `GATE_BASE_URL` 이 실제 접속 주소(https)와 같은지 |
| 모든 잠긴 주소가 503 | stock 서버 로그의 `[gate] 로드 실패` — 잠금 모듈 오류(안전하게 막힌 상태) |
| 급히 풀어야 할 때 | `.env` 에 `GATE_ENABLED=0` 추가 후 stock 서버 재시작 |
